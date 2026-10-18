"""Exercise the live admission webhook using server dry-run, without starting bad Pods."""
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

context = sys.argv[1]
if context not in ('kind-team4', 'team4-eks'):
    raise SystemExit('Unexpected context')
cmd = ['kubectl', '--context', context]
def read(*args):
    return json.loads(subprocess.check_output(cmd + list(args), text=True))
deployment = read('-n', 'demo', 'get', 'deployment', 'server', '-o', 'json')
pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'team4-admission-test', 'namespace': 'demo'},
       'spec': deployment['spec']['template']['spec']}
results = []
def check(name, obj, policy=None):
    response = subprocess.run(cmd + ['create', '--dry-run=server', '-f', '-', '-o', 'name'],
                              input=json.dumps(obj), text=True, capture_output=True)
    passed = response.returncode == 0 if policy is None else response.returncode != 0 and policy in response.stderr
    results.append({'test': name, 'result': 'PASS' if passed else 'FAIL',
                    'response': (response.stdout + response.stderr).strip()})
    print(f'{results[-1]["result"]}: {name}')
    if not passed:
        print(response.stderr)
    return passed

# Positive control must pass first; webhook outages cannot qualify as policy rejection.
for attempt in range(10):
    if check('valid-security-context', pod): break
    results.pop()
    time.sleep(2)
else:
    raise SystemExit('FAIL: valid Pod rejected; stop negative tests')
for name, field, value in [('root-user', 'runAsUser', 0), ('privileged', 'privileged', True),
                           ('privilege-escalation', 'allowPrivilegeEscalation', True),
                           ('writable-root-filesystem', 'readOnlyRootFilesystem', False)]:
    bad = copy.deepcopy(pod)
    bad['spec']['containers'][0].setdefault('securityContext', {})[field] = value
    if name == 'privileged':
        # Kubernetes rejects privileged=true + allowPrivilegeEscalation=false
        # before admission. Use a schema-valid Pod so Kyverno is the rejecting actor.
        bad['spec']['containers'][0]['securityContext']['allowPrivilegeEscalation'] = True
    check(name, bad, 'team4-restricted')
policies = read('get', 'clusterpolicies', '-o', 'json')
names = {p['metadata']['name'] for p in policies['items']}
if 'team4-approved-images' in names:
    for name, image in [('unapproved-repository', 'docker.io/library/busybox:latest'),
                         ('mutable-tag', pod['spec']['containers'][0]['image'].split('@')[0] + ':latest')]:
        bad = copy.deepcopy(pod)
        bad['spec']['containers'][0]['image'] = image
        check(name, bad, 'team4-approved-images')
    if os.environ.get('UNSIGNED_TEST_IMAGE'):
        bad = copy.deepcopy(pod)
        bad['spec']['containers'][0]['image'] = os.environ['UNSIGNED_TEST_IMAGE']
        check('unsigned-ecr-image', bad, 'team4-verify-signatures')
    else:
        results.append({'test': 'unsigned-ecr-image', 'result': 'NOT_TESTED', 'reason': 'UNSIGNED_TEST_IMAGE not provided'})
else:
    results.append({'test': 'ecr-signature-policy', 'result': 'NOT_TESTED', 'reason': 'ECR policies not configured in local mode'})
Path(f'evidence/admission-{context}.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
raise SystemExit(any(item['result'] == 'FAIL' for item in results))
