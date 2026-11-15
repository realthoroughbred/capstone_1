"""Allowlisted CloudWatch result -> redacted Slack message. Disabled by default.

Webhook transport is at-least-once: a crash after Slack accepts and before the
receipt is persisted can duplicate a message. Stable event IDs make this visible.
"""
import base64
import gzip
import hashlib
import io
import json
import os
import re
import urllib.request
from urllib.parse import urlparse
try:
    from .common import audit, dry_run, identity, require, required
    from .idempotency import claim, finish
except ImportError:
    from common import audit, dry_run, identity, require, required
    from idempotency import claim, finish

STATUSES = {'REMEDIATED', 'VERIFIED', 'FAILED', 'REJECTED', 'DRY_RUN', 'ALREADY_COMPLIANT', 'BUILD_STARTED'}


def message(result, event_id):
    require(result.get('status') in STATUSES, 'unsupported_notification_status')
    # Only operational identifiers, never arbitrary reason/event/Secret text.
    fields = []
    for key in ['status', 'resource_id', 'kind', 'safe_digest', 'source_commit', 'verification']:
        value = str(result.get(key, 'UNAVAILABLE'))
        require(len(value) <= 200 and re.fullmatch(r'[A-Za-z0-9_.:/@-]+', value), 'invalid_notification_identifier')
        fields.append(f'{key}={value}')
    return {'text': '[capstone_1 security demo] ' + ' | '.join(fields) + f' | event={event_id}'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('webhook_redirect_refused')


def post(url, payload):
    parsed = urlparse(url)
    require(parsed.scheme == 'https' and parsed.netloc == 'hooks.slack.com'
            and parsed.path.startswith('/services/') and not parsed.query and not parsed.fragment,
            'webhook_destination_not_allowed')
    request = urllib.request.Request(url, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=8) as response:
            require(response.status == 200 and response.read(64).strip() == b'ok', 'slack_rejected_message')
    except Exception:
        raise RuntimeError('slack_delivery_failed') from None


def notify(event, env, clients, send=post):
    account, _ = identity(env)
    raw = base64.b64decode(event['awslogs']['data'], validate=True)
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        decoded = stream.read(1_048_577)
    require(len(decoded) <= 1_048_576, 'notification_payload_too_large')
    data = json.loads(decoded)
    require(data.get('owner') == account, 'notification_account_mismatch')
    allowed = json.loads(required(env, 'ALLOWED_LOG_GROUPS'))
    require(data.get('logGroup') in allowed, 'notification_log_group_not_allowlisted')
    if data.get('messageType') == 'CONTROL_MESSAGE':
        return {'status': 'IGNORED_CONTROL'}
    require(data.get('messageType') == 'DATA_MESSAGE', 'unexpected_notification_envelope')
    enabled = env.get('SLACK_ENABLED', 'false') == 'true' and not dry_run(env)
    results = []
    for item in data['logEvents']:
        try:
            result = json.loads(item['message'])
        except (TypeError, ValueError):
            continue  # Runtime/START lines are not result documents.
        if not isinstance(result, dict) or result.get('status') not in STATUSES:
            continue
        key = hashlib.sha256((data['logGroup'] + ':' + item['id']).encode()).hexdigest()
        payload = message(result, key)
        if not enabled:
            results.append({'status': 'DRY_RUN', 'message': payload})
            continue
        table = required(env, 'IDEMPOTENCY_TABLE')
        owner = claim(clients['dynamodb'], table, 'slack:' + key)
        if owner is None:
            results.append({'status': 'DUPLICATE', 'event_id': key})
            continue
        try:
            arn = required(env, 'SLACK_SECRET_ARN')
            require(arn.startswith(f'arn:aws:secretsmanager:{env["EXPECTED_REGION"]}:{account}:secret:'), 'slack_secret_scope_mismatch')
            value = clients['secretsmanager'].get_secret_value(SecretId=arn)['SecretString']
            send(value, payload)
            finish(clients['dynamodb'], table, 'slack:' + key, owner, True)
            results.append({'status': 'SENT', 'event_id': key})
        except Exception:
            finish(clients['dynamodb'], table, 'slack:' + key, owner, False)
            raise RuntimeError('notification_delivery_failed') from None
    return {'notifications': results}


def lambda_handler(event, context):
    import boto3
    clients = {s: boto3.client(s, region_name=os.environ['EXPECTED_REGION']) for s in ['dynamodb', 'secretsmanager']}
    try:
        return audit(notify(event, os.environ, clients))
    except Exception:
        audit({'status': 'FAILED', 'component': 'slack-notifier', 'reason': 'notification_failed'})
        raise RuntimeError('notification_failed') from None
