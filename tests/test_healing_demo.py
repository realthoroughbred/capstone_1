"""Offline tests of the real-cloud demonstration's explicit approval gate."""

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from automation.common import Rejected
from automation.sg_demo import demonstrate


ACCOUNT, REGION, SG = "123456789012", "ap-northeast-2", "sg-0123456789abcdef0"
NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


class DemoEC2:
    def __init__(self):
        self.rules = []
        self.injected = False
        self.inject_calls = []
        self.revoke_calls = []
        self.polls = 0
        self.autoheal = True
        self.attached = False
        self.fail_after_inject = False

    def describe_security_groups(self, **kwargs):
        return {"SecurityGroups": [{"GroupId": SG, "OwnerId": ACCOUNT,
            "Tags": [{"Key": "Project", "Value": "team4"}, {"Key": "DemoOnly", "Value": "true"}]}]}

    def describe_network_interfaces(self, **kwargs):
        return {"NetworkInterfaces": [{"NetworkInterfaceId": "eni-attached"}] if self.attached else []}

    def describe_security_group_rules(self, **kwargs):
        if self.injected:
            self.polls += 1
            if self.autoheal and self.polls >= 2:
                self.rules = []
        return {"SecurityGroupRules": copy.deepcopy(self.rules)}

    def authorize_security_group_ingress(self, **kwargs):
        self.inject_calls.append(kwargs)
        self.injected = True
        self.rules = [{"GroupId": SG, "SecurityGroupRuleId": "sgr-created-by-this-run", "IsEgress": False,
                       "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "CidrIpv4": "0.0.0.0/0",
                       "Description": kwargs["IpPermissions"][0]["IpRanges"][0]["Description"]}]
        if self.fail_after_inject:
            raise TimeoutError("API response lost; rule may exist")
        return {"SecurityGroupRules": copy.deepcopy(self.rules)}

    def revoke_security_group_ingress(self, **kwargs):
        self.revoke_calls.append(kwargs)
        self.rules = [rule for rule in self.rules if rule["SecurityGroupRuleId"] not in kwargs["SecurityGroupRuleIds"]]
        return {"Return": True}


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.elapsed = 0
        self.options = SimpleNamespace(account=ACCOUNT, region=REGION, project="team4", security_group_id=SG,
            function_name="team4-sg-healing", config_rule="team4-restricted-ssh", approved_demo=False,
            timeout_seconds=60, poll_seconds=2)
        self.ec2 = DemoEC2()
        self.clients = {key: Mock() for key in ("sts", "lambda", "configservice", "logs")}
        self.clients["ec2"] = self.ec2
        self.clients["sts"].get_caller_identity.return_value = {"Account": ACCOUNT}
        self.clients["lambda"].get_function_configuration.return_value = {
            "FunctionArn": f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:team4-sg-healing",
            "State": "Active", "LastUpdateStatus": "Successful", "Environment": {"Variables": {
                "EXPECTED_ACCOUNT_ID": ACCOUNT, "EXPECTED_REGION": REGION, "PROJECT": "team4",
                "CONFIG_RULE_NAME": "team4-restricted-ssh", "ALLOWED_SECURITY_GROUP_IDS": SG, "DRY_RUN": "false"}}}
        self.clients["configservice"].describe_config_rules.return_value = {"ConfigRules": [{
            "ConfigRuleState": "ACTIVE", "Source": {"Owner": "AWS", "SourceIdentifier": "INCOMING_SSH_DISABLED"}}]}
        self.clients["configservice"].get_compliance_details_by_resource.side_effect = self.evaluation
        self.clients["logs"].filter_log_events.side_effect = self.logs

    def evaluation(self, **kwargs):
        state = "COMPLIANT" if not self.ec2.injected or not self.ec2.rules else "NON_COMPLIANT"
        when = NOW - timedelta(seconds=10) if not self.ec2.injected else NOW + timedelta(seconds=self.elapsed)
        return {"EvaluationResults": [{"ComplianceType": state, "ResultRecordedTime": when.isoformat(),
            "EvaluationResultIdentifier": {"OrderingTimestamp": when.isoformat(), "EvaluationResultQualifier": {
                "ConfigRuleName": "team4-restricted-ssh", "ResourceId": SG, "ResourceType": "AWS::EC2::SecurityGroup"}}}]}

    def logs(self, **kwargs):
        if self.ec2.rules:
            return {"events": []}
        return {"events": [{"message": json.dumps({"status": "REMEDIATED", "resource_id": SG,
            "event_origin": "CONFIG_EVENT",
            "dry_run": False, "verification": "PASS", "before_rule_ids": ["sgr-created-by-this-run"],
            "after_rule_ids": [], "config_rule_name": "team4-restricted-ssh", "trigger_compliance": "NON_COMPLIANT",
            "config_result_recorded_at": NOW.isoformat(), "config_ordering_time": NOW.isoformat(),
            "handler_duration_ms": 100})}]}

    def sleep(self, seconds):
        self.elapsed += seconds

    def run_demo(self):
        return demonstrate(self.options, self.clients, now=lambda: NOW + timedelta(seconds=self.elapsed),
                           monotonic=lambda: self.elapsed, sleep=self.sleep)

    def test_no_approval_means_read_only_preflight(self):
        self.assertEqual("PREFLIGHT_PASS", self.run_demo()["status"])
        self.assertEqual([], self.ec2.inject_calls)
        self.assertEqual([], self.ec2.revoke_calls)

    def test_approved_live_flow_requires_config_and_lambda_proof(self):
        self.options.approved_demo = True
        result = self.run_demo()
        self.assertEqual("VERIFIED", result["status"])
        self.assertEqual("PASS", result["verification"])
        self.assertEqual("NOT_NEEDED", result["cleanup"])
        self.assertIn("injection_to_config_recorded_seconds", result)
        self.assertIn("injection_to_removal_observed_seconds", result)
        self.assertEqual(1, len(self.ec2.inject_calls))
        self.assertEqual([], self.ec2.revoke_calls)
        self.clients["lambda"].invoke.assert_not_called()

    def test_attached_group_is_never_injected(self):
        self.options.approved_demo = True
        self.ec2.attached = True
        with self.assertRaisesRegex(Rejected, "network_interfaces"):
            self.run_demo()
        self.assertEqual([], self.ec2.inject_calls)

    def test_dry_run_lambda_prevents_injection(self):
        self.options.approved_demo = True
        self.clients["lambda"].get_function_configuration.return_value["Environment"]["Variables"]["DRY_RUN"] = "true"
        with self.assertRaisesRegex(Rejected, "enable_live_healing"):
            self.run_demo()
        self.assertEqual([], self.ec2.inject_calls)

    def test_timeout_removes_own_rule_without_claiming_autoheal(self):
        self.options.approved_demo = True
        self.options.poll_seconds = 30
        self.ec2.autoheal = False
        result = self.run_demo()
        self.assertEqual("FAILED", result["status"])
        self.assertEqual("FAIL", result["verification"])
        self.assertEqual("OWN_TEST_RULE_REMOVED", result["cleanup"])
        self.assertEqual([], self.ec2.rules)
        self.assertEqual(["sgr-created-by-this-run"], self.ec2.revoke_calls[0]["SecurityGroupRuleIds"])

    def test_removed_rule_without_lambda_log_is_not_verified(self):
        self.options.approved_demo = True
        self.options.poll_seconds = 30
        self.clients["logs"].filter_log_events.side_effect = lambda **kwargs: {"events": []}
        self.assertEqual("FAILED", self.run_demo()["status"])
        self.assertEqual([], self.ec2.revoke_calls)

    def test_uncertain_injection_is_cleaned_by_unique_marker(self):
        self.options.approved_demo = True
        self.ec2.autoheal = False
        self.ec2.fail_after_inject = True
        result = self.run_demo()
        self.assertEqual("FAILED", result["status"])
        self.assertEqual("OWN_TEST_RULE_REMOVED", result["cleanup"])
        self.assertEqual([], self.ec2.rules)

    def test_wrong_account_never_injects(self):
        self.options.approved_demo = True
        self.clients["sts"].get_caller_identity.return_value = {"Account": "999999999999"}
        with self.assertRaisesRegex(Rejected, "caller_account"):
            self.run_demo()
        self.assertEqual([], self.ec2.inject_calls)

    def test_old_config_trigger_cannot_supply_new_detection_proof(self):
        self.options.approved_demo = True
        self.options.poll_seconds = 30
        original_evaluation = self.evaluation
        def compliant_only(**kwargs):
            result = original_evaluation(**kwargs)
            result["EvaluationResults"][0]["ComplianceType"] = "COMPLIANT"
            return result
        self.clients["configservice"].get_compliance_details_by_resource.side_effect = compliant_only
        original_logs = self.logs
        def old_log(**kwargs):
            result = original_logs(**kwargs)
            if result["events"]:
                event = json.loads(result["events"][0]["message"])
                event["config_ordering_time"] = (NOW - timedelta(minutes=1)).isoformat()
                result["events"][0]["message"] = json.dumps(event)
            return result
        self.clients["logs"].filter_log_events.side_effect = old_log
        self.assertEqual("FAILED", self.run_demo()["status"])

    def test_external_attachment_after_injection_stops_and_flags_cleanup(self):
        self.options.approved_demo = True
        self.ec2.autoheal = False
        original = self.ec2.authorize_security_group_ingress
        def inject_and_attach(**kwargs):
            result = original(**kwargs)
            self.ec2.attached = True
            return result
        self.ec2.authorize_security_group_ingress = inject_and_attach
        result = self.run_demo()
        self.assertEqual("FAILED", result["status"])
        self.assertEqual("MANUAL_REVIEW_REQUIRED", result["cleanup"])
        self.assertEqual([], self.ec2.revoke_calls)


if __name__ == "__main__":
    unittest.main()
