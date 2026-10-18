"""Read-only account/inventory checks. Never prints credentials or secret values."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--profile', required=True)
parser.add_argument('--account', required=True)
parser.add_argument('--region', default='ap-northeast-2')
args = parser.parse_args()
common = ['--profile', args.profile, '--region', args.region, '--output', 'json', '--no-cli-pager']

def run(arguments):
    response = subprocess.run(['aws'] + arguments + common, text=True, capture_output=True)
    return response.returncode, response.stdout, response.stderr

code, stdout, stderr = run(['sts', 'get-caller-identity'])
if code:
    raise SystemExit('AWS authentication failed; log in locally. No credentials were logged.')
identity = json.loads(stdout)
if identity['Account'] != args.account or identity['Arn'].endswith(':root'):
    raise SystemExit('Wrong AWS account or forbidden root identity')
checks = {
    'eks': ['eks', 'list-clusters'],
    'project_vpcs': ['ec2', 'describe-vpcs', '--filters', 'Name=tag:Project,Values=team4'],
    'config_recorders': ['configservice', 'describe-configuration-recorders'],
    'ecr': ['ecr', 'describe-repositories'],
    'oidc_providers': ['iam', 'list-open-id-connect-providers'],
}
results = []
for name, command in checks.items():
    code, stdout, stderr = run(command)
    entry = {'name': name, 'command': 'aws ' + ' '.join(command + common), 'exit_code': code,
             'result': 'PASS' if code == 0 else 'BLOCKED'}
    if code == 0:
        entry['inventory'] = json.loads(stdout)
    else:
        entry['reason'] = 'AccessDenied' if 'not authorized' in stderr or 'AccessDenied' in stderr else 'AWS API failure; inspect permission/network/session'
    results.append(entry)
report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'scope': 'aws', 'read_only': True,
          'identity': identity, 'profile': args.profile, 'region': args.region, 'checks': results}
target = Path('evidence/aws')
target.mkdir(parents=True, exist_ok=True)
(target / 'preflight.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'account': identity['Account'], 'arn': identity['Arn'], 'checks': [{k:v for k,v in c.items() if k != 'inventory'} for c in results]}, indent=2))
raise SystemExit(1 if any(c['result'] != 'PASS' for c in results) else 0)
