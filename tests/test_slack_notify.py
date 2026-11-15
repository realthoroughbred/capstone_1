"""Mock transport only: no Slack messages are transmitted."""
import base64
import gzip
import json
import unittest
from unittest.mock import Mock
from automation.slack_notify import notify, message, post
from automation.common import Rejected
from test_resource_healing import AwsFailure

ENV = {'EXPECTED_ACCOUNT_ID': '123456789012', 'EXPECTED_REGION': 'ap-northeast-2',
       'ALLOWED_LOG_GROUPS': '["/aws/lambda/team4-sg-healing"]', 'IDEMPOTENCY_TABLE': 'test',
       'SLACK_SECRET_ARN': 'arn:aws:secretsmanager:ap-northeast-2:123456789012:secret:test'}


def event(status='REMEDIATED'):
    data = {'owner': ENV['EXPECTED_ACCOUNT_ID'], 'logGroup': '/aws/lambda/team4-sg-healing',
            'messageType': 'DATA_MESSAGE', 'logEvents': [{'id': '1', 'message': json.dumps({
                'status': status, 'resource_id': 'sg-synthetic', 'secret': 'DO-NOT-LEAK',
                'event': {'token': 'DO-NOT-LEAK'}})}]}
    return {'awslogs': {'data': base64.b64encode(gzip.compress(json.dumps(data).encode())).decode()}}


class SlackTests(unittest.TestCase):
    def test_disabled_by_default_and_redacted(self):
        send = Mock()
        result = notify(event(), ENV, {}, send)
        self.assertEqual(result['notifications'][0]['status'], 'DRY_RUN')
        self.assertNotIn('DO-NOT-LEAK', json.dumps(result))
        send.assert_not_called()

    def test_mock_success_failure_and_duplicate(self):
        for status in ['REMEDIATED', 'FAILED']:
            db, sm, send = Mock(), Mock(), Mock()
            sm.get_secret_value.return_value = {'SecretString': 'synthetic-url-not-transmitted'}
            clients = {'dynamodb': db, 'secretsmanager': sm}
            env = {**ENV, 'DRY_RUN': 'false', 'SLACK_ENABLED': 'true'}
            result = notify(event(status), env, clients, send)
            self.assertEqual(result['notifications'][0]['status'], 'SENT')
            self.assertEqual(send.call_count, 1)
            db.put_item.side_effect = AwsFailure('ConditionalCheckFailedException')
            self.assertEqual(notify(event(status), env, clients, send)['notifications'][0]['status'], 'DUPLICATE')
            self.assertEqual(send.call_count, 1)

    def test_delivery_failure_remains_retryable(self):
        db, sm = Mock(), Mock()
        sm.get_secret_value.return_value = {'SecretString': 'synthetic'}
        with self.assertRaisesRegex(RuntimeError, 'delivery_failed'):
            notify(event(), {**ENV, 'DRY_RUN': 'false', 'SLACK_ENABLED': 'true'},
                   {'dynamodb': db, 'secretsmanager': sm}, Mock(side_effect=TimeoutError))
        self.assertEqual(db.update_item.call_args.kwargs['ExpressionAttributeValues'][':state']['S'], 'FAILED')

    def test_unapproved_destination_and_mentions_refused_without_network(self):
        with self.assertRaises(Rejected): post('https://example.com/services/a', {})
        with self.assertRaises(Rejected): message({'status': 'FAILED', 'resource_id': '<!channel>'}, 'test')
        with self.assertRaises(Rejected): notify(event(), {**ENV, 'ALLOWED_LOG_GROUPS': '[]'}, {})
