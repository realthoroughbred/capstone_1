import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('aws_preflight', Path(__file__).parents[1] / 'scripts/aws-preflight.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ACCOUNT = '123456789012'
IDENTITY = {'Account': ACCOUNT, 'Arn': f'arn:aws:iam::{ACCOUNT}:user/test-operator'}


class PreflightTests(unittest.TestCase):
    def inspect(self, run):
        return module.inspect('test-profile', ACCOUNT, 'ap-northeast-2', run)

    def test_expired_session_replaces_old_pass_and_preserves_history(self):
        run = Mock(return_value=(1, '', 'Your session has expired. PRIVATE_TOKEN_SENTINEL'))
        result = self.inspect(run)
        self.assertEqual(result['authentication']['reason'], 'SessionExpired')
        self.assertEqual(result['checks'], [])
        run.assert_called_once_with(['sts', 'get-caller-identity'])
        with tempfile.TemporaryDirectory() as folder:
            old = {'result': 'PASS', 'checks': [{'result': 'PASS'}]}
            module.save_report(old, folder)
            module.save_report(result, folder)
            latest = (Path(folder) / 'preflight.json').read_text()
            self.assertEqual(json.loads(latest)['result'], 'BLOCKED')
            self.assertNotIn('PRIVATE_TOKEN_SENTINEL', latest)
            archive = list(Path(folder).glob('preflight-*.json'))
            self.assertEqual(len(archive), 1)
            self.assertEqual(json.loads(archive[0].read_text()), old)

    def test_wrong_account_and_root_stop_before_inventory(self):
        for identity in [{'Account': '999999999999', 'Arn': 'arn:aws:iam::999999999999:user/other'},
                         {'Account': ACCOUNT, 'Arn': f'arn:aws:iam::{ACCOUNT}:root'}]:
            run = Mock(return_value=(0, json.dumps(identity), ''))
            result = self.inspect(run)
            self.assertEqual(result['result'], 'BLOCKED')
            self.assertNotIn('identity', result)
            self.assertEqual(run.call_count, 1)

    def test_invalid_identity_response_stops_inventory(self):
        for response in ['not json', 'null', '{}']:
            run = Mock(return_value=(0, response, ''))
            self.assertEqual(self.inspect(run)['result'], 'BLOCKED')
            self.assertEqual(run.call_count, 1)

    def test_denied_inventory_is_not_reported_as_empty_pass(self):
        run = Mock(side_effect=[(0, json.dumps(IDENTITY), '')] +
                   [(1, '', 'AccessDenied: PRIVATE_TOKEN_SENTINEL')] + [(0, '{}', '')] * 4)
        report = self.inspect(run)
        self.assertEqual(report['result'], 'BLOCKED')
        self.assertEqual(report['authentication']['result'], 'PASS')
        self.assertEqual(report['checks'][0]['reason'], 'AccessDenied')
        self.assertNotIn('inventory', report['checks'][0])
        self.assertNotIn('PRIVATE_TOKEN_SENTINEL', json.dumps(report))

    def test_invalid_inventory_blocks_success(self):
        run = Mock(side_effect=[(0, json.dumps(IDENTITY), '')] + [(0, '[]', '')] * 5)
        report = self.inspect(run)
        self.assertEqual(report['result'], 'BLOCKED')
        self.assertTrue(all(c['reason'] == 'InvalidInventoryResponse' for c in report['checks']))

    def test_success_requires_all_five_read_only_checks(self):
        run = Mock(side_effect=[(0, json.dumps(IDENTITY), '')] + [(0, '{}', '')] * 5)
        report = self.inspect(run)
        self.assertEqual(report['result'], 'PASS')
        self.assertEqual({c['name'] for c in report['checks']}, set(module.CHECKS))
        self.assertTrue(report['read_only'])
        self.assertEqual([c.args[0] for c in run.call_args_list[1:]], list(module.CHECKS.values()))


if __name__ == '__main__':
    unittest.main()
