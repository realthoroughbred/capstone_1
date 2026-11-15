"""Mock service responses only. No AWS requests or real violations."""
import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from automation import resource_healing as h
from automation.common import Rejected
from automation.idempotency import claim

ACCOUNT = '123456789012'
ENV = {'EXPECTED_ACCOUNT_ID': ACCOUNT, 'EXPECTED_REGION': 'ap-northeast-2', 'PROJECT': 'team4',
       'SANDBOX_BUCKET': f'team4-{ACCOUNT}-ap-northeast-2-healing-sandbox',
       'SANDBOX_ROLE': 'team4-healing-sandbox', 'SCHEDULE_RULE_ARN': 'arn:test:schedule',
       'IDEMPOTENCY_TABLE': 'synthetic', 'SOURCE_COMMIT': 'a' * 40}


class AwsFailure(Exception):
    def __init__(self, code):
        self.response = {'Error': {'Code': code}}


def clients():
    s3, iam, db, sts = Mock(), Mock(), Mock(), Mock()
    tags = [{'Key': 'Project', 'Value': 'team4'}, {'Key': 'DemoOnly', 'Value': 'true'}]
    s3.get_bucket_tagging.return_value = {'TagSet': copy.deepcopy(tags)}
    s3.list_object_versions.return_value = {}
    state = {'block': dict.fromkeys(h.BLOCK, False), 'policy': {'Version': '2012-10-17', 'Statement': []}}
    s3.get_public_access_block.side_effect = lambda **k: {'PublicAccessBlockConfiguration': copy.deepcopy(state['block'])}
    s3.put_public_access_block.side_effect = lambda **k: state.update(block=k['PublicAccessBlockConfiguration'])
    iam.get_role.return_value = {'Role': {'Arn': f'arn:aws:iam::{ACCOUNT}:role/team4-sandbox/team4-healing-sandbox',
        'Tags': tags, 'AssumeRolePolicyDocument': {'Statement': [{'Effect': 'Deny'}]}}}
    iam.list_attached_role_policies.return_value = {'AttachedPolicies': []}
    iam.list_role_policies.return_value = {'PolicyNames': ['sandbox-deny-all']}
    iam.get_role_policy.side_effect = lambda **k: {'PolicyDocument': copy.deepcopy(state['policy'])}
    iam.put_role_policy.side_effect = lambda **k: state.update(policy=json.loads(k['PolicyDocument']))
    sts.get_caller_identity.return_value = {'Account': ACCOUNT}
    return {'s3': s3, 'iam': iam, 'dynamodb': db, 'sts': sts}, state


class ResourceHealingTests(unittest.TestCase):
    def test_default_dry_run_never_writes(self):
        c, _ = clients()
        for kind in ['s3', 'iam']:
            self.assertEqual(h.repair(kind, ENV, c)['status'], 'DRY_RUN')
        c['s3'].put_public_access_block.assert_not_called()
        c['iam'].put_role_policy.assert_not_called()

    def test_live_mock_repair_rechecks_and_repeat_is_noop(self):
        c, _ = clients()
        for kind in ['s3', 'iam']:
            result = h.repair(kind, {**ENV, 'DRY_RUN': 'false'}, c, sleep=lambda _: None)
            self.assertEqual(result['status'], 'REMEDIATED')
            self.assertNotEqual(result['before_sha256'], result['after_sha256'])
            self.assertEqual(h.repair(kind, {**ENV, 'DRY_RUN': 'false'}, c)['status'], 'ALREADY_COMPLIANT')
        self.assertEqual(c['s3'].put_public_access_block.call_count, 1)
        self.assertEqual(c['iam'].put_role_policy.call_count, 1)

    def test_nonempty_bucket_and_real_role_are_refused(self):
        c, _ = clients()
        c['s3'].list_object_versions.return_value = {'Versions': [{}]}
        with self.assertRaises(Rejected): h.repair('s3', {**ENV, 'DRY_RUN': 'false'}, c)
        c['iam'].get_role.return_value['Role']['AssumeRolePolicyDocument']['Statement'][0]['Effect'] = 'Allow'
        with self.assertRaises(Rejected): h.repair('iam', {**ENV, 'DRY_RUN': 'false'}, c)
        c['iam'].put_role_policy.assert_not_called()

    def test_missing_permissions_is_not_compliance(self):
        c, _ = clients()
        c['s3'].get_public_access_block.side_effect = AwsFailure('AccessDenied')
        with self.assertRaises(AwsFailure): h.repair('s3', ENV, c)
        c['s3'].put_public_access_block.assert_not_called()

    def test_failed_repair_verification_is_failure(self):
        c, _ = clients()
        c['s3'].put_public_access_block.side_effect = None
        with self.assertRaisesRegex(Rejected, 'reverification'):
            h.repair('s3', {**ENV, 'DRY_RUN': 'false'}, c, sleep=lambda _: None)

    def test_outside_allowlist_and_changed_tags_refused(self):
        c, _ = clients()
        with self.assertRaises(Rejected): h.repair('s3', {**ENV, 'SANDBOX_BUCKET': 'production'}, c)
        c['s3'].get_bucket_tagging.side_effect = [{'TagSet': [{'Key': 'Project', 'Value': 'team4'}, {'Key': 'DemoOnly', 'Value': 'true'}]}, {'TagSet': []}]
        with self.assertRaises(Rejected): h.repair('s3', {**ENV, 'DRY_RUN': 'false'}, c)
        c['s3'].put_public_access_block.assert_not_called()

    def test_duplicate_schedule_does_not_repair(self):
        c, _ = clients()
        c['dynamodb'].put_item.side_effect = AwsFailure('ConditionalCheckFailedException')
        event = {'source': 'aws.events', 'detail-type': 'Scheduled Event', 'account': ACCOUNT,
                 'region': ENV['EXPECTED_REGION'], 'resources': [ENV['SCHEDULE_RULE_ARN']],
                 'id': 'synthetic-id', 'time': '2026-11-16T00:00:00Z'}
        r = h.respond(event, {**ENV, 'DRY_RUN': 'false'}, c, now=datetime(2026, 11, 16, tzinfo=timezone.utc))
        self.assertEqual(r['status'], 'DUPLICATE')
        c['s3'].get_bucket_tagging.assert_not_called()

    def test_idempotency_permission_failure_fails_closed(self):
        db = Mock()
        db.put_item.side_effect = AwsFailure('AccessDeniedException')
        with self.assertRaisesRegex(RuntimeError, 'store_unavailable'): claim(db, 'test', 'id')

    def test_evidence_failure_does_not_mark_event_done(self):
        c, _ = clients()
        event = {'source':'aws.events','detail-type':'Scheduled Event','account':ACCOUNT,
                 'region':ENV['EXPECTED_REGION'],'resources':[ENV['SCHEDULE_RULE_ARN']],
                 'id':'synthetic-id','time':'2026-11-16T00:00:00Z'}
        with self.assertRaises(RuntimeError):
            h.respond(event,{**ENV,'DRY_RUN':'false'},c,now=datetime(2026,11,16,tzinfo=timezone.utc),
                      publish=Mock(side_effect=RuntimeError('synthetic evidence outage')))
        self.assertEqual(c['dynamodb'].update_item.call_args.kwargs['ExpressionAttributeValues'][':state']['S'],'FAILED')
