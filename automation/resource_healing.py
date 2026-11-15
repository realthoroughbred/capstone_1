"""Poll and repair ONLY the dedicated empty S3 bucket and unassumable IAM test role.

No caller-supplied target or policy is accepted. Default is dry-run. Scheduling
avoids relying on regional delivery of global IAM CloudTrail events. It does not
promise one-second detection. The SG handler and its protections are independent.
"""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
try:
    from .common import Rejected, audit, aws_error_code, dry_run, evidence, identity, require, required, timestamp
    from .idempotency import claim, finish
except ImportError:
    from common import Rejected, audit, aws_error_code, dry_run, evidence, identity, require, required, timestamp
    from idempotency import claim, finish

BLOCK = dict.fromkeys(['BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets'], True)
DENY = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Deny', 'Action': '*', 'Resource': '*'}]}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def tagged(tags, project):
    values = {tag['Key']: tag['Value'] for tag in tags}
    require(values.get('Project') == project and values.get('DemoOnly') == 'true', 'sandbox_tags_mismatch')


def bucket_state(s3, bucket, account, project):
    tagged(s3.get_bucket_tagging(Bucket=bucket, ExpectedBucketOwner=account)['TagSet'], project)
    # Refuse nonempty buckets, including old versions/delete markers. No object is read.
    versions = s3.list_object_versions(Bucket=bucket, ExpectedBucketOwner=account, MaxKeys=1)
    require(not versions.get('Versions') and not versions.get('DeleteMarkers') and not versions.get('IsTruncated'), 'sandbox_bucket_not_empty')
    try:
        return s3.get_public_access_block(Bucket=bucket, ExpectedBucketOwner=account)['PublicAccessBlockConfiguration']
    except Exception as exc:
        if aws_error_code(exc) == 'NoSuchPublicAccessBlockConfiguration':
            return dict.fromkeys(BLOCK, False)
        raise


def role_state(iam, role, account, project, policy):
    obj = iam.get_role(RoleName=role)['Role']
    require(obj.get('Arn') == f'arn:aws:iam::{account}:role/{project}-sandbox/{role}', 'sandbox_role_scope_mismatch')
    tagged(obj.get('Tags', []), project)
    trust = obj['AssumeRolePolicyDocument'].get('Statement', [])
    require(bool(trust) and all(s.get('Effect') == 'Deny' for s in trust), 'sandbox_role_must_be_unassumable')
    attached = iam.list_attached_role_policies(RoleName=role)
    require(not attached.get('AttachedPolicies') and not attached.get('IsTruncated'), 'sandbox_has_attached_policies')
    inline = iam.list_role_policies(RoleName=role)
    require(inline.get('PolicyNames') == [policy] and not inline.get('IsTruncated'), 'sandbox_inline_policy_scope_mismatch')
    return iam.get_role_policy(RoleName=role, PolicyName=policy)['PolicyDocument']


def repair(kind, env, clients, sleep=time.sleep):
    account, _ = identity(env)
    project = required(env, 'PROJECT')
    dry = dry_run(env)
    if kind == 's3':
        target = required(env, 'SANDBOX_BUCKET')
        require(target == f'{project}-{account}-{env["EXPECTED_REGION"]}-healing-sandbox', 'bucket_not_allowlisted')
        read = lambda: bucket_state(clients['s3'], target, account, project)
        mutate = lambda: clients['s3'].put_public_access_block(Bucket=target, ExpectedBucketOwner=account, PublicAccessBlockConfiguration=BLOCK)
        desired = BLOCK
    else:
        require(kind == 'iam', 'unknown_repair_kind')
        target = required(env, 'SANDBOX_ROLE')
        require(target == project + '-healing-sandbox', 'role_not_allowlisted')
        policy = 'sandbox-deny-all'
        read = lambda: role_state(clients['iam'], target, account, project, policy)
        mutate = lambda: clients['iam'].put_role_policy(RoleName=target, PolicyName=policy, PolicyDocument=canonical(DENY))
        desired = DENY
    before = read()
    compliant = canonical(before) == canonical(desired)
    # IAM policy content is intentionally not logged; hash proves before/after.
    result = {'kind': kind, 'resource_id': target, 'dry_run': dry,
              'before_sha256': hashlib.sha256(canonical(before).encode()).hexdigest(),
              'status': 'ALREADY_COMPLIANT' if compliant else 'DRY_RUN',
              'verification': 'PASS' if compliant else 'NOT_EXECUTED'}
    after = before
    if not compliant and not dry:
        require(canonical(read()) == canonical(before), 'sandbox_changed_before_repair')
        mutate()
        for attempt in range(3):
            after = read()  # Recheck ownership/tags/emptiness/trust as well as policy.
            if canonical(after) == canonical(desired):
                break
            sleep(0.5 * (attempt + 1))
        require(canonical(after) == canonical(desired), 'sandbox_reverification_failed')
        result.update(status='REMEDIATED', verification='PASS')
    result['after_sha256'] = hashlib.sha256(canonical(after).encode()).hexdigest()
    return result


def respond(event, env, clients, now=None, sleep=time.sleep, publish=lambda result: None):
    now = now or datetime.now(timezone.utc)
    account, region = identity(env)
    require(event.get('source') == 'aws.events' and event.get('detail-type') == 'Scheduled Event', 'unexpected_event')
    require(event.get('account') == account and event.get('region') == region, 'event_scope_mismatch')
    require(event.get('resources') == [required(env, 'SCHEDULE_RULE_ARN')], 'schedule_not_allowlisted')
    require(isinstance(event.get('id'), str) and bool(event['id']), 'event_id_missing')
    require(-300 <= (now - timestamp(event.get('time'))).total_seconds() <= 3600, 'event_time_out_of_range')
    require(clients['sts'].get_caller_identity()['Account'] == account, 'caller_account_mismatch')
    dry = dry_run(env)
    table = required(env, 'IDEMPOTENCY_TABLE') if not dry else None
    key = 'resource-scan:' + hashlib.sha256(event['id'].encode()).hexdigest()
    owner = claim(clients['dynamodb'], table, key) if not dry else None
    if not dry and owner is None:
        return {'status': 'DUPLICATE', 'event_id': event['id'], 'dry_run': False}
    try:
        results = []
        for kind in ['s3', 'iam']:
            result = repair(kind, env, clients, sleep)
            result.update(event_id=event['id'], source_event_time=event['time'],
                          verified_at=datetime.now(timezone.utc).isoformat(),
                          source_commit=env.get('SOURCE_COMMIT', 'UNAVAILABLE'),
                          event_origin='SIMULATED_EVENT' if event.get('_evidence_kind') == 'SIMULATED_FIXTURE' else 'AWS_SCHEDULED_POLL')
            publish(result)
            results.append(result)
        if owner:
            finish(clients['dynamodb'], table, key, owner, True)
        return {'status': 'SCAN_COMPLETE', 'dry_run': dry, 'results': results}
    except Exception:
        if owner:
            finish(clients['dynamodb'], table, key, owner, False)
        raise


def lambda_handler(event, context):
    import boto3
    from botocore.config import Config
    config = Config(connect_timeout=3, read_timeout=5, retries={'max_attempts': 2, 'mode': 'standard'})
    clients = {s: boto3.client(s, region_name=os.environ['EXPECTED_REGION'], config=config)
               for s in ['s3', 'iam', 'sts', 'dynamodb']}
    try:
        result = respond(event, os.environ, clients,
                         publish=lambda item: evidence(item, os.environ, clients['s3'], 'resource-healing'))
        return audit(result)
    except Rejected as exc:
        audit({'status': 'REJECTED', 'reason': str(exc), 'component': 'resource-healing'})
        raise RuntimeError('resource_healing_rejected') from None
    except Exception:
        audit({'status': 'FAILED', 'reason': 'resource_remediation_or_evidence_failed', 'component': 'resource-healing'})
        raise RuntimeError('resource_healing_failed') from None
