"""Offline behavioral tests; fake clients never connect to AWS."""

import copy
import unittest

from automation.common import Rejected
from automation.sg_healing import remediate


ACCOUNT = "123456789012"
SG = "sg-0123456789abcdef0"
ENV = {"EXPECTED_ACCOUNT_ID": ACCOUNT, "EXPECTED_REGION": "ap-northeast-2",
       "PROJECT": "team4", "DEMO_SECURITY_GROUP_ID": SG, "CONFIG_RULE_NAME": "team4-restricted-ssh"}
EVENT = {"source": "aws.config", "detail-type": "Config Rules Compliance Change",
         "account": ACCOUNT, "region": "ap-northeast-2", "detail": {
             "configRuleName": "team4-restricted-ssh", "newEvaluationResult": {
                 "complianceType": "NON_COMPLIANT", "evaluationResultIdentifier": {
                     "evaluationResultQualifier": {"resourceType": "AWS::EC2::SecurityGroup", "resourceId": SG}}}}}


def rule(rule_id="sgr-public-ssh", **changes):
    return dict({"SecurityGroupRuleId": rule_id, "GroupId": SG, "IsEgress": False,
                 "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "CidrIpv4": "0.0.0.0/0"}, **changes)


class ApiError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class STS:
    def get_caller_identity(self):
        return {"Account": ACCOUNT}


class EC2:
    def __init__(self, rules=None):
        self.rules = copy.deepcopy(rules if rules is not None else [rule()])
        self.group = {"GroupId": SG, "OwnerId": ACCOUNT, "Tags": [
            {"Key": "Project", "Value": "team4"}, {"Key": "DemoOnly", "Value": "true"}]}
        self.enis = []
        self.calls = []
        self.revoke_error = None
        self.keep_rule = False
        self.attach_on_second_check = False
        self.checks = 0

    def describe_security_groups(self, **kwargs):
        return {"SecurityGroups": [self.group]}

    def describe_network_interfaces(self, **kwargs):
        self.checks += 1
        if self.attach_on_second_check and self.checks > 1:
            self.enis = [{"NetworkInterfaceId": "eni-attached"}]
        return {"NetworkInterfaces": self.enis}

    def describe_security_group_rules(self, **kwargs):
        return {"SecurityGroupRules": copy.deepcopy(self.rules)}

    def revoke_security_group_ingress(self, **kwargs):
        self.calls.append(kwargs)
        if not self.keep_rule:
            self.rules = [r for r in self.rules if r["SecurityGroupRuleId"] not in kwargs["SecurityGroupRuleIds"]]
        if self.revoke_error:
            raise ApiError(self.revoke_error)
        return {"Return": True}


class HealingTests(unittest.TestCase):
    def run_healing(self, ec2=None, event=None, env=None):
        self.ec2 = ec2 or EC2()
        return remediate(event or copy.deepcopy(EVENT), env or dict(ENV), self.ec2, STS(), sleep=lambda _: None)

    def test_defaults_to_dry_run_without_mutation(self):
        result = self.run_healing()
        self.assertEqual("DRY_RUN", result["status"])
        self.assertEqual("NOT_EXECUTED", result["verification"])
        self.assertEqual([], self.ec2.calls)

    def test_removes_only_world_ssh_ipv4_and_ipv6_then_verifies(self):
        ec2 = EC2([rule(), rule("sgr-v6", CidrIpv4=None, CidrIpv6="::/0"),
                   rule("sgr-private", CidrIpv4="10.40.0.0/16"),
                   rule("sgr-web", FromPort=443, ToPort=443), rule("sgr-egress", IsEgress=True)])
        result = self.run_healing(ec2, env=dict(ENV, DRY_RUN="false"))
        self.assertEqual("REMEDIATED", result["status"])
        self.assertEqual("PASS", result["verification"])
        self.assertEqual({"sgr-private", "sgr-web", "sgr-egress"},
                         {r["SecurityGroupRuleId"] for r in ec2.rules})
        self.assertTrue(all(c["GroupId"] == SG for c in ec2.calls))

    def test_duplicate_event_is_idempotent(self):
        ec2 = EC2()
        self.run_healing(ec2, env=dict(ENV, DRY_RUN="false"))
        result = self.run_healing(ec2, env=dict(ENV, DRY_RUN="false"))
        self.assertEqual("ALREADY_COMPLIANT", result["status"])
        self.assertEqual(1, len(ec2.calls))

    def test_account_region_source_and_allowlist_fail_closed(self):
        for key, value in (("account", "999999999999"), ("region", "us-east-1"), ("source", "custom.test")):
            with self.subTest(key=key):
                ec2 = EC2()
                with self.assertRaises(Rejected):
                    self.run_healing(ec2, event=dict(EVENT, **{key: value}), env=dict(ENV, DRY_RUN="false"))
                self.assertEqual([], ec2.calls)
        with self.assertRaisesRegex(Rejected, "not_allowlisted"):
            self.run_healing(env=dict(ENV, DEMO_SECURITY_GROUP_ID="sg-other", DRY_RUN="false"))

    def test_tags_and_owner_fail_closed(self):
        for change in ({"Tags": []}, {"OwnerId": "999999999999"}):
            with self.subTest(change=change):
                ec2 = EC2()
                ec2.group.update(change)
                with self.assertRaises(Rejected):
                    self.run_healing(ec2, env=dict(ENV, DRY_RUN="false"))
                self.assertEqual([], ec2.calls)

    def test_attached_network_interface_refused(self):
        ec2 = EC2()
        ec2.enis = [{"NetworkInterfaceId": "eni-production"}]
        with self.assertRaisesRegex(Rejected, "network_interfaces"):
            self.run_healing(ec2, env=dict(ENV, DRY_RUN="false"))
        self.assertEqual([], ec2.calls)

    def test_attachment_rechecked_before_write(self):
        ec2 = EC2()
        ec2.attach_on_second_check = True
        with self.assertRaisesRegex(Rejected, "network_interfaces"):
            self.run_healing(ec2, env=dict(ENV, DRY_RUN="false"))
        self.assertEqual([], ec2.calls)

    def test_empty_filtered_eni_page_is_followed_before_proving_absence(self):
        ec2 = EC2()
        requests = []
        def pages(**kwargs):
            requests.append(copy.deepcopy(kwargs))
            return ({"NetworkInterfaces": [], "NextToken": "page2"} if 'NextToken' not in kwargs
                    else {"NetworkInterfaces": []})
        ec2.describe_network_interfaces = pages
        self.assertEqual('DRY_RUN', self.run_healing(ec2)['status'])
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]['NextToken'], 'page2')
        self.assertEqual(requests[0]['Filters'], requests[1]['Filters'])

    def test_attachment_on_later_eni_page_prevents_mutation(self):
        ec2 = EC2()
        ec2.describe_network_interfaces = lambda **kw: (
            {"NetworkInterfaces": [], "NextToken": "page2"} if 'NextToken' not in kw
            else {"NetworkInterfaces": [{"NetworkInterfaceId": "eni-attached"}]})
        with self.assertRaisesRegex(Rejected, 'security_group_has_network_interfaces'):
            self.run_healing(ec2, env=dict(ENV, DRY_RUN='false'))
        self.assertEqual(ec2.calls, [])

    def test_repeated_or_unbounded_eni_pages_prevent_mutation(self):
        for repeated in (True, False):
            ec2 = EC2()
            calls = []
            def pages(**kwargs):
                calls.append(kwargs)
                return {"NetworkInterfaces": [], "NextToken": 'same' if repeated else str(len(calls))}
            ec2.describe_network_interfaces = pages
            with self.assertRaisesRegex(Rejected, 'network_interfaces_pagination'):
                self.run_healing(ec2, env=dict(ENV, DRY_RUN='false'))
            self.assertLessEqual(len(calls), 20)
            self.assertEqual(ec2.calls, [])

    def test_broad_rule_requires_manual_review_without_partial_remediation(self):
        for broad in (rule("sgr-all", IpProtocol="-1"), rule("sgr-range", FromPort=0, ToPort=65535)):
            with self.subTest(broad=broad):
                ec2 = EC2([rule(), broad])
                with self.assertRaisesRegex(Rejected, "manual_review"):
                    self.run_healing(ec2, env=dict(ENV, DRY_RUN="false"))
                self.assertEqual([], ec2.calls)

    def test_concurrent_already_deleted_rule_is_verified(self):
        ec2 = EC2()
        ec2.revoke_error = "InvalidSecurityGroupRuleId.NotFound"
        self.assertEqual("REMEDIATED", self.run_healing(ec2, env=dict(ENV, DRY_RUN="false"))["status"])

    def test_permission_failure_does_not_claim_success(self):
        ec2 = EC2()
        ec2.revoke_error = "UnauthorizedOperation"
        with self.assertRaisesRegex(RuntimeError, "revoke_failed"):
            self.run_healing(ec2, env=dict(ENV, DRY_RUN="false"))

    def test_failed_reverification_raises(self):
        ec2 = EC2()
        ec2.keep_rule = True
        with self.assertRaisesRegex(RuntimeError, "verification_failed"):
            self.run_healing(ec2, env=dict(ENV, DRY_RUN="false"))

    def test_invalid_dry_run_value_rejected(self):
        with self.assertRaisesRegex(Rejected, "invalid_dry_run"):
            self.run_healing(env=dict(ENV, DRY_RUN="yes"))

    def test_compliant_event_ignored(self):
        event = copy.deepcopy(EVENT)
        event["detail"]["newEvaluationResult"]["complianceType"] = "COMPLIANT"
        self.assertEqual("IGNORED", self.run_healing(event=event)["status"])

    def test_rule_pagination_cannot_hide_violation(self):
        ec2 = EC2()
        requests = []
        def pages(**kwargs):
            requests.append(kwargs)
            return ({"SecurityGroupRules": [], "NextToken": "page2"} if "NextToken" not in kwargs
                    else {"SecurityGroupRules": [rule()]})
        ec2.describe_security_group_rules = pages
        self.assertEqual("DRY_RUN", self.run_healing(ec2)["status"])
        self.assertEqual(2, len(requests))


if __name__ == "__main__":
    unittest.main()
