"""Remove exact world SSH rules from an explicitly allowlisted, unattached demo SG.

DRY_RUN defaults true. Broad rules that also expose SSH require manual review;
this function never revokes unrelated protocols, ports, or private CIDRs.
"""

import os
import time

try:
    from .common import (Rejected, audit, aws_error_code, dry_run, evidence, identity, notify_slack, post_json,
                         require, required, timestamp)
except ImportError:  # Lambda archive has these modules at its root.
    from common import (Rejected, audit, aws_error_code, dry_run, evidence, identity, notify_slack, post_json,
                        require, required, timestamp)

# Constant failure codes raised by remediate(); only these may be shown in Slack.
_FAILURE_REASONS = ("security_group_revoke_failed", "security_group_verification_failed")


def _rules(ec2, group_id):
    result = []
    request = {"Filters": [{"Name": "group-id", "Values": [group_id]}]}
    while True:
        response = ec2.describe_security_group_rules(**request)
        result.extend(response.get("SecurityGroupRules", []))
        token = response.get("NextToken")
        if not token:
            return result
        request["NextToken"] = token


def _exposes_ssh(rule):
    if rule.get("IsEgress") is not False:
        return False
    if rule.get("CidrIpv4") != "0.0.0.0/0" and rule.get("CidrIpv6") != "::/0":
        return False
    if rule.get("IpProtocol") == "-1":
        return True
    return (rule.get("IpProtocol") in ("tcp", "6")
            and isinstance(rule.get("FromPort"), int)
            and isinstance(rule.get("ToPort"), int)
            and rule["FromPort"] <= 22 <= rule["ToPort"])


def _validate_target(ec2, group_id, account, project):
    response = ec2.describe_security_groups(GroupIds=[group_id])
    groups = response.get("SecurityGroups", [])
    require(len(groups) == 1, "security_group_not_found")
    group = groups[0]
    require(group.get("GroupId") == group_id and group.get("OwnerId") == account,
            "security_group_owner_mismatch")
    tags = {item["Key"]: item["Value"] for item in group.get("Tags", [])}
    require(tags.get("Project") == project and tags.get("DemoOnly") == "true",
            "security_group_tags_mismatch")
    # EC2 can return an empty filtered page with a continuation token. Follow
    # every page before proving absence; any attachment or incomplete traversal
    # still refuses mutation. Bound calls and reject repeating tokens.
    request = {"Filters": [{"Name": "group-id", "Values": [group_id]}], "MaxResults": 1000}
    seen = set()
    for _ in range(20):
        enis = ec2.describe_network_interfaces(**request)
        require(not enis.get("NetworkInterfaces"), "security_group_has_network_interfaces")
        token = enis.get("NextToken")
        if not token:
            return
        require(token not in seen, "network_interfaces_pagination_repeated")
        seen.add(token)
        request["NextToken"] = token
    raise Rejected("network_interfaces_pagination_incomplete")


def remediate(event, env, ec2, sts, sleep=time.sleep):
    started = time.monotonic()
    account, region = identity(env)
    project = required(env, "PROJECT")
    dry = dry_run(env)
    allowed = {value.strip() for value in env.get("ALLOWED_SECURITY_GROUP_IDS", "").split(",") if value.strip()}
    if env.get("DEMO_SECURITY_GROUP_ID"):
        allowed.add(env["DEMO_SECURITY_GROUP_ID"])
    require(bool(allowed), "missing_security_group_allowlist")
    require(event.get("source") == "aws.config"
            and event.get("detail-type") == "Config Rules Compliance Change", "unexpected_event_type")
    require(event.get("account") == account and event.get("region") == region, "event_scope_mismatch")
    detail = event.get("detail", {})
    require(detail.get("configRuleName") == required(env, "CONFIG_RULE_NAME"), "config_rule_mismatch")
    evaluation = detail.get("newEvaluationResult", {})
    if evaluation.get("complianceType") != "NON_COMPLIANT":
        return {"status": "IGNORED", "reason": "not_non_compliant", "dry_run": dry}
    qualifier = evaluation.get("evaluationResultIdentifier", {}).get("evaluationResultQualifier", {})
    require(qualifier.get("resourceType") == "AWS::EC2::SecurityGroup", "unexpected_resource_type")
    group_id = qualifier.get("resourceId")
    require(group_id in allowed, "security_group_not_allowlisted")
    require(sts.get_caller_identity().get("Account") == account, "caller_account_mismatch")
    _validate_target(ec2, group_id, account, project)
    before = [rule for rule in _rules(ec2, group_id) if _exposes_ssh(rule)]
    for rule in before:
        require(rule.get("GroupId") == group_id, "rule_group_mismatch")
        require(rule.get("IpProtocol") in ("tcp", "6")
                and rule.get("FromPort") == 22 and rule.get("ToPort") == 22,
                "broad_ssh_rule_requires_manual_review")
        require(isinstance(rule.get("SecurityGroupRuleId"), str), "missing_rule_id")
    result = {"status": "ALREADY_COMPLIANT", "resource_id": group_id,
              "account": account, "region": region, "dry_run": dry,
              "before_rule_ids": sorted(rule["SecurityGroupRuleId"] for rule in before),
              "after_rule_ids": [], "verification": "PASS", "action": "none"}
    result["event_origin"] = ("SIMULATED_EVENT" if event.get("_evidence_kind") == "SIMULATED_FIXTURE"
                              else "CONFIG_EVENT")
    result["before_rules"] = [{key: rule[key] for key in (
        "SecurityGroupRuleId", "IpProtocol", "FromPort", "ToPort", "CidrIpv4", "CidrIpv6") if key in rule}
        for rule in before]
    result["after_rules"] = []
    result["config_rule_name"] = env["CONFIG_RULE_NAME"]
    result["trigger_compliance"] = "NON_COMPLIANT"
    for key, value in (("source_event_time", event.get("time")),
                       ("config_result_recorded_at", evaluation.get("resultRecordedTime")),
                       ("config_ordering_time", evaluation.get("evaluationResultIdentifier", {}).get("orderingTimestamp"))):
        if value:
            result[key] = timestamp(value).isoformat()
    if before and dry:
        result.update(status="DRY_RUN", after_rule_ids=result["before_rule_ids"],
                      after_rules=result["before_rules"],
                      verification="NOT_EXECUTED", action="would_revoke_world_ssh")
    elif before:
        for rule in before:
            # Recheck tags and attachments immediately before each mutation.
            _validate_target(ec2, group_id, account, project)
            try:
                ec2.revoke_security_group_ingress(
                    GroupId=group_id, SecurityGroupRuleIds=[rule["SecurityGroupRuleId"]])
            except Exception as exc:
                if aws_error_code(exc) not in ("InvalidSecurityGroupRuleId.NotFound", "InvalidPermission.NotFound"):
                    raise RuntimeError("security_group_revoke_failed") from None
        remaining = []
        for attempt in range(3):
            remaining = [rule for rule in _rules(ec2, group_id) if _exposes_ssh(rule)]
            if not remaining:
                break
            if attempt < 2:
                sleep(0.5 * (attempt + 1))
        if remaining:
            raise RuntimeError("security_group_verification_failed")
        _validate_target(ec2, group_id, account, project)
        result.update(status="REMEDIATED", action="revoked_world_ssh")
    result["handler_duration_ms"] = round((time.monotonic() - started) * 1000)
    return result


def _event_target(event):
    # Untrusted: notify_slack only displays it after matching the sg-ID format.
    try:
        return event["detail"]["newEvaluationResult"]["evaluationResultIdentifier"][
            "evaluationResultQualifier"]["resourceId"]
    except (KeyError, TypeError):
        return None


def handle(event, env, make_clients, get_secrets, post=post_json, clock=time.monotonic):
    """Remediate, persist evidence, then report to Slack.

    make_clients() returns (ec2, sts, s3). The Slack report runs last and is
    best-effort, so it can neither delay a revoke nor change the outcome.
    """
    started = clock()
    target = _event_target(event)

    def report(result):
        # Slack must never replace the return value or the exception of the caller
        # (the callers below are inside or right before their own raise/return).
        try:
            duration = result.get("handler_duration_ms")
            if duration is None:  # REJECTED/FAILED never reach the end of remediate().
                duration = round((clock() - started) * 1000)
            notify_slack(result, env, get_secrets, target=target, duration_ms=duration, post=post)
        except Exception:
            pass

    try:
        ec2, sts, s3 = make_clients()
        result = remediate(event, env, ec2, sts)
    except Rejected as exc:
        result = audit({"status": "REJECTED", "reason": str(exc)})
        report(result)
        return result
    except Exception as exc:
        failed = audit({"status": "FAILED", "reason": "remediation_or_verification_failed"})
        known = isinstance(exc, RuntimeError) and str(exc) in _FAILURE_REASONS
        report(dict(failed, reason=str(exc) if known else failed["reason"]))
        # Sanitized failure activates Lambda retries and the failure destination.
        raise RuntimeError("remediation_or_verification_failed") from None
    # The security group outcome is final here. A failed evidence write must not turn
    # a successful revoke into a reported FAILED: record and report the real result,
    # then fail the invocation exactly as before so Lambda retries the write.
    try:
        result = evidence(result, env, s3, "sg-healing")
    except Exception:
        unsaved = audit(dict(result, evidence_saved=False))
        audit({"status": "FAILED", "reason": "evidence_write_failed"})
        report(unsaved)
        raise RuntimeError("remediation_or_verification_failed") from None
    report(result)
    return result


def lambda_handler(event, context):
    region = os.environ.get("EXPECTED_REGION")

    def make_clients():
        import boto3
        from botocore.config import Config
        config = Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2, "mode": "standard"})
        return (boto3.client("ec2", region_name=region, config=config),
                boto3.client("sts", region_name=region, config=config),
                boto3.client("s3", region_name=region, config=config))

    def get_secrets():
        import boto3
        from botocore.config import Config
        # Tight limits: Slack is optional and must not hold the invocation open.
        # total_max_attempts counts the first request, so 1 means no retry at all.
        # (max_attempts counts retries after the first request: 1 would mean two tries.)
        config = Config(connect_timeout=2, read_timeout=3,
                        retries={"total_max_attempts": 1, "mode": "standard"})
        return boto3.client("secretsmanager", region_name=region, config=config)

    return handle(event, os.environ, make_clients, get_secrets)
