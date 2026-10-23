"""Read-only account/inventory checks. Never prints credentials or secret values."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


CHECKS = {
    'eks': ['eks', 'list-clusters'],
    'project_vpcs': ['ec2', 'describe-vpcs', '--filters', 'Name=tag:Project,Values=team4'],
    'config_recorders': ['configservice', 'describe-configuration-recorders'],
    'ecr': ['ecr', 'describe-repositories'],
    'oidc_providers': ['iam', 'list-open-id-connect-providers'],
}


def failure_reason(error):
    """Return only an allowlisted label, never raw CLI output or credential details."""
    text = error.lower()
    if any(word in text for word in ('session has expired', 'expiredtoken', 'token has expired')):
        return 'SessionExpired'
    if any(word in text for word in ('not authorized', 'accessdenied', 'unauthorizedoperation')):
        return 'AccessDenied'
    return 'AuthenticationOrApiFailure'


def aws_runner(profile, region):
    def run(arguments):
        try:
            response = subprocess.run(
                ['aws'] + arguments + ['--profile', profile, '--region', region,
                                      '--output', 'json', '--no-cli-pager'],
                text=True, capture_output=True, timeout=30)
            return response.returncode, response.stdout, response.stderr
        except (OSError, subprocess.TimeoutExpired):
            return 1, '', 'AWS CLI unavailable or timed out'
    return run


def inspect(profile, account, region, run):
    report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'scope': 'aws',
              'read_only': True, 'profile': profile, 'region': region,
              'expected_account': account, 'result': 'BLOCKED', 'checks': []}
    code, stdout, stderr = run(['sts', 'get-caller-identity'])
    reason = failure_reason(stderr) if code else None
    identity = None
    if not code:
        try:
            identity = json.loads(stdout)
        except (ValueError, TypeError):
            reason = 'InvalidIdentityResponse'
        if not isinstance(identity, dict):
            reason = 'InvalidIdentityResponse'
        elif identity.get('Account') != account:
            reason = 'AccountMismatch'
        elif not isinstance(identity.get('Arn'), str) or not identity['Arn'].startswith(
                (f'arn:aws:iam::{account}:user/', f'arn:aws:sts::{account}:assumed-role/')):
            reason = 'UnexpectedOrRootIdentity'
    if reason:
        report['authentication'] = {'result': 'BLOCKED', 'reason': reason}
        return report
    report['authentication'] = {'result': 'PASS'}
    report['identity'] = identity
    for name, command in CHECKS.items():
        code, stdout, stderr = run(command)
        entry = {'name': name, 'command': 'aws ' + ' '.join(command), 'exit_code': code,
                 'result': 'PASS' if code == 0 else 'BLOCKED'}
        if code == 0:
            try:
                inventory = json.loads(stdout)
                if not isinstance(inventory, dict):
                    raise ValueError('Expected an inventory object')
                entry['inventory'] = inventory
            except (ValueError, TypeError):
                entry.update(result='BLOCKED', reason='InvalidInventoryResponse')
        else:
            entry['reason'] = failure_reason(stderr)
        report['checks'].append(entry)
    if all(c['result'] == 'PASS' for c in report['checks']):
        report['result'] = 'PASS'
    return report


def save_report(report, directory):
    """Archive the previous observation before replacing the current result, including failures."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    latest = directory / 'preflight.json'
    if latest.is_file():
        previous = latest.read_bytes()
        archive = directory / ('preflight-' + hashlib.sha256(previous).hexdigest()[:16] + '.json')
        if not archive.exists():
            archive.write_bytes(previous)
    temporary = directory / 'preflight.pending.json'
    temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    temporary.replace(latest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--account', required=True)
    parser.add_argument('--region', default='ap-northeast-2')
    args = parser.parse_args()
    if len(args.account) != 12 or not args.account.isascii() or not args.account.isdigit():
        parser.error('--account must contain exactly 12 ASCII digits')
    report = inspect(args.profile, args.account, args.region, aws_runner(args.profile, args.region))
    save_report(report, Path(__file__).resolve().parents[1] / 'evidence/aws')
    summary = {k: v for k, v in report.items() if k != 'checks'}
    summary['checks'] = [{k: v for k, v in check.items() if k != 'inventory'}
                         for check in report['checks']]
    print(json.dumps(summary, indent=2))
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
