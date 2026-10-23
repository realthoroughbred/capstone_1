"""Approved real-cloud SG experiment; no mutation unless explicitly requested.

The experiment never invokes Lambda or fabricates a Config event. It observes
Config evaluations and Lambda logs, and tracks only its own injected SG rule.
"""

import argparse
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .common import Rejected, require, timestamp
from .inspector_worker import AwsService, execute
from .sg_healing import _exposes_ssh, _rules, _validate_target


def evaluations(config, group_id, rule_name):
    # The operator can read this project's tagged Config rule. Filter its
    # paginated results to the exact target instead of requiring account-wide
    # GetComplianceDetailsByResource permission.
    request = {"ConfigRuleName": rule_name,
               "ComplianceTypes": ["COMPLIANT", "NON_COMPLIANT"]}
    matches = []
    while True:
        response = config.get_compliance_details_by_config_rule(**request)
        for item in response.get("EvaluationResults", []):
            qualifier = item.get("EvaluationResultIdentifier", {}).get("EvaluationResultQualifier", {})
            if (qualifier.get("ConfigRuleName") == rule_name
                    and qualifier.get("ResourceId") == group_id
                    and qualifier.get("ResourceType") == "AWS::EC2::SecurityGroup"):
                matches.append(item)
        if not response.get("NextToken"):
            return matches
        request["NextToken"] = response["NextToken"]


def parse_time(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return timestamp(value)


def recorded_at(item):
    return parse_time(item.get("ResultRecordedTime"))


def matching_log(logs, function, group_id, rule_id, started):
    request = {"logGroupName": "/aws/lambda/" + function,
               "startTime": int(started.timestamp() * 1000),
               "filterPattern": '{ $.resource_id = "' + group_id + '" }', "limit": 100}
    # Cap one polling pass; repeated passes cover ingestion delay. No raw message
    # is copied to the evidence; only the handler's explicit proof fields are used.
    for _ in range(5):
        response = logs.filter_log_events(**request)
        for item in response.get("events", []):
            try:
                record = json.loads(item.get("message", ""))
            except ValueError:
                continue
            if (isinstance(record, dict) and record.get("resource_id") == group_id
                    and record.get("status") == "REMEDIATED"
                    and record.get("dry_run") is False
                    and record.get("event_origin") == "CONFIG_EVENT"
                    and rule_id in record.get("before_rule_ids", [])
                    and record.get("after_rule_ids") == [] and record.get("verification") == "PASS"):
                return {key: record[key] for key in ("config_rule_name", "trigger_compliance",
                    "source_event_time", "config_result_recorded_at", "config_ordering_time",
                    "handler_duration_ms") if key in record}
        token = response.get("nextToken")
        if not token or token == request.get("nextToken"):
            break
        request["nextToken"] = token
    return None


def demonstrate(options, clients, now=lambda: datetime.now(timezone.utc),
                monotonic=time.monotonic, sleep=time.sleep):
    account, region, group_id = options.account, options.region, options.security_group_id
    require(re.fullmatch(r"[0-9]{12}", account), "invalid_account")
    require(re.fullmatch(r"sg-[a-f0-9]{8,17}", group_id), "invalid_security_group")
    require(60 <= options.timeout_seconds <= 1800, "timeout_must_be_60_to_1800_seconds")
    require(1 <= options.poll_seconds <= 30, "poll_must_be_1_to_30_seconds")
    require(clients["sts"].get_caller_identity().get("Account") == account, "caller_account_mismatch")
    ec2, config = clients["ec2"], clients["configservice"]
    _validate_target(ec2, group_id, account, options.project)
    require(not any(_exposes_ssh(rule) for rule in _rules(ec2, group_id)), "baseline_already_exposes_ssh")
    function = clients["lambda"].get_function_configuration(FunctionName=options.function_name)
    require(function.get("FunctionArn") == f"arn:aws:lambda:{region}:{account}:function:{options.function_name}",
            "lambda_scope_mismatch")
    require(function.get("State") == "Active" and function.get("LastUpdateStatus") == "Successful",
            "lambda_not_ready")
    env = function.get("Environment", {}).get("Variables", {})
    require(env.get("EXPECTED_ACCOUNT_ID") == account and env.get("EXPECTED_REGION") == region
            and env.get("PROJECT") == options.project and env.get("CONFIG_RULE_NAME") == options.config_rule,
            "lambda_scope_configuration_mismatch")
    allowed = {value.strip() for value in env.get("ALLOWED_SECURITY_GROUP_IDS", "").split(",")}
    allowed.add(env.get("DEMO_SECURITY_GROUP_ID", ""))
    require(group_id in allowed, "lambda_security_group_not_allowlisted")
    rules = config.describe_config_rules(ConfigRuleNames=[options.config_rule]).get("ConfigRules", [])
    require(len(rules) == 1 and rules[0].get("ConfigRuleState") == "ACTIVE"
            and rules[0].get("Source", {}).get("Owner") == "AWS"
            and rules[0].get("Source", {}).get("SourceIdentifier") == "INCOMING_SSH_DISABLED",
            "restricted_ssh_rule_not_active")
    baseline = evaluations(config, group_id, options.config_rule)
    require(bool(baseline) and max(baseline, key=recorded_at).get("ComplianceType") == "COMPLIANT",
            "config_compliant_baseline_required")
    result = {"status": "PREFLIGHT_PASS", "account": account, "region": region,
              "security_group_id": group_id, "config_rule": options.config_rule,
              "function_name": options.function_name, "approved_demo": options.approved_demo,
              "evidence_kind": "REAL_AWS_OBSERVATION", "verification": "NOT_EXECUTED",
              "preflight_at": now().isoformat(), "lambda_dry_run": env.get("DRY_RUN", "true"),
              "cleanup": "NOT_NEEDED"}
    if not options.approved_demo:
        return result
    require(env.get("DRY_RUN", "true") == "false", "enable_live_healing_before_approved_demo")
    _validate_target(ec2, group_id, account, options.project)
    description = "approved-team4-ssh-demo-" + uuid.uuid4().hex
    started, deadline = now(), monotonic() + options.timeout_seconds
    result.update(status="FAILED", injection_requested_at=started.isoformat(), injection_marker=description)
    rule_id = None
    try:
        injected = ec2.authorize_security_group_ingress(GroupId=group_id, IpPermissions=[{
            "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
            "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": description}]}])
        created = injected.get("SecurityGroupRules", [])
        require(len(created) == 1 and bool(created[0].get("SecurityGroupRuleId")), "injection_result_uncertain")
        rule_id = created[0]["SecurityGroupRuleId"]
        result.update(injected_rule_id=rule_id, injection_completed_at=now().isoformat())
        proof = None
        while monotonic() < deadline:
            _validate_target(ec2, group_id, account, options.project)
            current = _rules(ec2, group_id)
            removed = not any(rule.get("SecurityGroupRuleId") == rule_id for rule in current)
            clean = not any(_exposes_ssh(rule) for rule in current)
            if removed and clean and "rule_removal_observed_at" not in result:
                result["rule_removal_observed_at"] = now().isoformat()
            for item in evaluations(config, group_id, options.config_rule):
                record_time = recorded_at(item)
                ordering = parse_time(item.get("EvaluationResultIdentifier", {}).get("OrderingTimestamp"))
                if record_time < started or ordering < started:
                    continue
                if item.get("ComplianceType") == "NON_COMPLIANT":
                    result.setdefault("config_noncompliant_recorded_at", record_time.isoformat())
                elif item.get("ComplianceType") == "COMPLIANT" and removed and clean:
                    result["config_compliant_recorded_at"] = record_time.isoformat()
            proof = matching_log(clients["logs"], options.function_name, group_id, rule_id, started) or proof
            if proof and proof.get("config_rule_name") == options.config_rule and proof.get("trigger_compliance") == "NON_COMPLIANT":
                result["lambda_remediation_proof"] = proof
                if (proof.get("config_result_recorded_at") and proof.get("config_ordering_time")
                        and timestamp(proof["config_result_recorded_at"]) >= started
                        and timestamp(proof["config_ordering_time"]) >= started):
                    result.setdefault("config_noncompliant_recorded_at", proof["config_result_recorded_at"])
            if (removed and clean and "lambda_remediation_proof" in result
                    and "config_noncompliant_recorded_at" in result and "config_compliant_recorded_at" in result):
                result.update(status="VERIFIED", verification="PASS", verified_at=now().isoformat())
                result["injection_to_removal_observed_seconds"] = round(
                    (timestamp(result["rule_removal_observed_at"]) - started).total_seconds(), 3)
                result["injection_to_config_recorded_seconds"] = round(
                    (timestamp(result["config_noncompliant_recorded_at"]) - started).total_seconds(), 3)
                break
            sleep(options.poll_seconds)
        if result["status"] != "VERIFIED":
            result["failure_reason"] = "timed_out_waiting_for_config_and_lambda_evidence"
    except Exception:
        result["failure_reason"] = "demo_api_or_precondition_failure"
    finally:
        # A failed experiment must not leave its test exposure behind. Discover
        # only the unique rule created by this run, including uncertain API outcomes.
        try:
            leftovers = [rule for rule in _rules(ec2, group_id)
                         if (rule_id and rule.get("SecurityGroupRuleId") == rule_id)
                         or rule.get("Description") == description]
            if leftovers:
                _validate_target(ec2, group_id, account, options.project)
                for rule in leftovers:
                    require(rule.get("Description") == description and rule.get("GroupId") == group_id
                            and rule.get("IpProtocol") in ("tcp", "6")
                            and rule.get("FromPort") == 22 and rule.get("ToPort") == 22
                            and rule.get("CidrIpv4") == "0.0.0.0/0", "test_rule_changed_requires_manual_review")
                    ec2.revoke_security_group_ingress(GroupId=group_id,
                        SecurityGroupRuleIds=[rule["SecurityGroupRuleId"]])
                remaining_ids = {rule["SecurityGroupRuleId"] for rule in _rules(ec2, group_id)}
                require(not any(rule["SecurityGroupRuleId"] in remaining_ids for rule in leftovers), "cleanup_not_verified")
                result.update(status="FAILED", verification="FAIL", cleanup="OWN_TEST_RULE_REMOVED")
            else:
                result["cleanup"] = "NOT_NEEDED" if rule_id else "MANUAL_REVIEW_REQUIRED"
        except Exception:
            result.update(status="FAILED", verification="FAIL", cleanup="MANUAL_REVIEW_REQUIRED")
    if result["status"] != "VERIFIED":
        result["verification"] = "FAIL"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", default="ap-northeast-2")
    parser.add_argument("--project", default="team4")
    parser.add_argument("--security-group-id", required=True)
    parser.add_argument("--function-name", required=True)
    parser.add_argument("--config-rule", required=True)
    parser.add_argument("--approved-demo", action="store_true", help="explicitly authorize one isolated world-SSH test rule and cleanup")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--evidence", default="evidence/aws/sg-healing-demo.json")
    options = parser.parse_args(argv)
    env = dict(os.environ, EXPECTED_REGION=options.region, AWS_PAGER="")
    clients = {name: AwsService(name, env, execute) for name in ("sts", "ec2", "configservice", "lambda", "logs")}
    try:
        result = demonstrate(options, clients)
    except Rejected as exc:
        result = {"status": "FAILED", "verification": "FAIL", "failure_reason": str(exc),
                  "evidence_kind": "REAL_AWS_ATTEMPT", "approved_demo": options.approved_demo}
    except Exception:
        result = {"status": "FAILED", "verification": "FAIL", "failure_reason": "preflight_failed",
                  "evidence_kind": "REAL_AWS_ATTEMPT", "approved_demo": options.approved_demo}
    destination = Path(options.evidence)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 1 if result["status"] == "FAILED" else 0
