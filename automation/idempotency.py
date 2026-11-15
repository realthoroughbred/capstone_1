"""Conditional leases: failed work is retryable; concurrent/finished work is not repeated."""
import time
import uuid
try:
    from .common import aws_error_code
except ImportError:
    from common import aws_error_code


def claim(db, table, key, now=None):
    now = int(time.time() if now is None else now)
    owner = uuid.uuid4().hex
    try:
        db.put_item(TableName=table, Item={'id': {'S': key}, 'owner': {'S': owner},
                    'status': {'S': 'PROCESSING'}, 'lease_until': {'N': str(now + 300)},
                    'expires_at': {'N': str(now + 7 * 86400)}},
                    ConditionExpression='attribute_not_exists(id) OR #s = :failed OR (#s = :processing AND lease_until < :now)',
                    ExpressionAttributeNames={'#s': 'status'},
                    ExpressionAttributeValues={':failed': {'S': 'FAILED'}, ':processing': {'S': 'PROCESSING'}, ':now': {'N': str(now)}})
    except Exception as exc:
        if aws_error_code(exc) == 'ConditionalCheckFailedException':
            return None
        raise RuntimeError('idempotency_store_unavailable') from None
    return owner


def finish(db, table, key, owner, success):
    db.update_item(TableName=table, Key={'id': {'S': key}},
                   UpdateExpression='SET #s = :state', ConditionExpression='#o = :owner AND #s = :processing',
                   ExpressionAttributeNames={'#s': 'status', '#o': 'owner'},
                   ExpressionAttributeValues={':state': {'S': 'DONE' if success else 'FAILED'},
                                              ':owner': {'S': owner}, ':processing': {'S': 'PROCESSING'}})
