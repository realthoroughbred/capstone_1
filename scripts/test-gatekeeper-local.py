"""Live local admission cases and separate runtime proof; never contacts EKS.

Each command/exit code/stdout/stderr is retained under a new evidence directory.
Only this run's generated Pods are removed. Existing workloads are untouched.
"""
import argparse
import copy
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def pod(name, image, namespace='son-policy-test'):
    return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name, 'namespace': namespace,
            'labels': {'app': 'integration-security-test'}},
            'spec': {'automountServiceAccountToken': False, 'restartPolicy': 'Never',
                     'securityContext': {'runAsUser': 10001, 'runAsNonRoot': True,
                                         'seccompProfile': {'type': 'RuntimeDefault'}},
                     'containers': [{'name': 'test', 'image': image, 'imagePullPolicy': 'IfNotPresent',
                                     'securityContext': {'allowPrivilegeEscalation': False,
                                                         'readOnlyRootFilesystem': True,
                                                         'capabilities': {'drop': ['ALL']}}}]}}


def cases(image):
    base = pod('integration-dry-run', image)
    result = [('pod-uid-nonroot', base, None, 'Gatekeeper')]
    for name, uid, flag, expected in [('pod-root', 0, True, 'son-require-nonroot'),
                                      ('flag-only', None, True, None),
                                      ('missing-security-settings', None, None, 'son-require-nonroot')]:
        obj = copy.deepcopy(base)
        sc = obj['spec']['securityContext']
        for key, value in [('runAsUser', uid), ('runAsNonRoot', flag)]:
            if value is None:
                sc.pop(key)
            else:
                sc[key] = value
        result.append((name, obj, expected, 'Gatekeeper'))
    obj = copy.deepcopy(base)
    obj['spec']['containers'][0]['securityContext']['runAsUser'] = 0
    result.append(('container-root-overrides-pod', obj, 'son-require-nonroot', 'Gatekeeper'))
    obj = copy.deepcopy(base)
    obj['spec']['securityContext']['runAsUser'] = 0
    obj['spec']['containers'][0]['securityContext']['runAsUser'] = 10001
    result.append(('container-nonroot-overrides-pod', obj, None, 'Gatekeeper'))
    obj = copy.deepcopy(base)
    obj['spec']['securityContext'].pop('runAsUser')
    obj['spec']['containers'][0]['securityContext']['runAsNonRoot'] = False
    result.append(('container-false-overrides-pod-flag', obj, 'son-require-nonroot', 'Gatekeeper'))
    obj = copy.deepcopy(base)
    init = copy.deepcopy(obj['spec']['containers'][0])
    init.update(name='init', command=['true'])
    init['securityContext']['runAsUser'] = 0
    obj['spec']['initContainers'] = [init]
    result.append(('root-init-container', obj, 'son-require-nonroot', 'Gatekeeper'))
    obj = copy.deepcopy(base)
    obj['spec']['containers'].append(copy.deepcopy(obj['spec']['containers'][0]))
    obj['spec']['containers'][1]['name'] = 'second'
    obj['spec']['containers'][1]['securityContext']['runAsUser'] = 0
    result.append(('second-container-root', obj, 'son-require-nonroot', 'Gatekeeper'))
    # The same complete security context is allowed by both independent engines.
    obj = pod('integration-dry-run', image, 'demo')
    result.append(('kyverno-valid', copy.deepcopy(obj), None, 'Kyverno'))
    bad = copy.deepcopy(obj)
    bad['spec']['securityContext']['runAsUser'] = 0
    result.append(('kyverno-root', bad, 'team4-restricted', 'Kyverno'))
    obj['spec']['containers'][0]['securityContext']['readOnlyRootFilesystem'] = False
    result.append(('kyverno-writable-rootfs', obj, 'team4-restricted', 'Kyverno'))
    obj = copy.deepcopy(base)
    obj['spec']['containers'][0]['securityContext']['readOnlyRootFilesystem'] = False
    result.append(('gatekeeper-does-not-own-rootfs-rule', obj, None, 'Gatekeeper'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--image', required=True, help='Already built and loaded into kind; immutable tag or digest')
    a = parser.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=False)
    cmd = ['kubectl', '--context', 'kind-team4', '--request-timeout=30s']
    results, created = [], []
    counter = 0

    def run(args, obj=None):
        nonlocal counter
        counter += 1
        start = datetime.now(timezone.utc).isoformat()
        invocation = cmd + args
        try:
            response = subprocess.run(invocation, input=json.dumps(obj) if obj is not None else None,
                                      text=True, capture_output=True, timeout=200)
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or b'').decode(errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or '')
            error = (exc.stderr or b'').decode(errors='replace') if isinstance(exc.stderr, bytes) else (exc.stderr or '')
            response = subprocess.CompletedProcess(invocation, 124, output, error + '\nCommand timed out')
        record = {'started_at': start, 'command': invocation, 'stdin': obj, 'exit_code': response.returncode,
                  'stdout': response.stdout, 'stderr': response.stderr}
        (a.output_dir / f'{counter:03d}-command.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        return response

    def check(name, args, obj=None, policy=None, engine=None, phase='server-dry-run'):
        response = run(args, obj)
        passed = response.returncode == 0 if policy is None else response.returncode != 0 and policy in response.stderr
        results.append({'test': name, 'phase': phase, 'expected_policy': policy, 'engine': engine,
                        'result': 'PASS' if passed else 'FAIL', 'command_record': f'{counter:03d}-command.json',
                        'decision': 'ALLOWED' if response.returncode == 0 else 'DENIED' if policy and policy in response.stderr else 'ERROR'})
        print(f"{results[-1]['result']} [{phase}] {name} ({engine})", flush=True)
        if not passed:
            print(response.stderr, flush=True)
        return passed, response

    try:
        config = run(['config', 'view', '--minify', '-o', 'jsonpath={.clusters[0].cluster.server}'])
        if config.returncode or urlparse(config.stdout).hostname not in {'localhost', '127.0.0.1', '::1'}:
            raise RuntimeError('Refusing non-local Kubernetes endpoint')
        for args in [['get', 'constrainttemplate', 'team4nonroot', '-o', 'json'],
                     ['get', 'team4nonroot', 'son-require-nonroot', '-o', 'json'],
                     ['get', 'clusterpolicy', 'team4-restricted', '-o', 'json']]:
            snapshot = run(args)
            if snapshot.returncode:
                raise RuntimeError('Both Gatekeeper and Kyverno must be installed')
        constraint = json.loads(run(['get', 'team4nonroot', 'son-require-nonroot', '-o', 'json']).stdout)
        scopes = constraint['spec'].get('scopedEnforcementActions', [])
        points = {p['name'] for action in scopes if action.get('action') == 'deny' for p in action['enforcementPoints']}
        if (constraint['spec']['match'].get('namespaces') != ['son-policy-test']
                or constraint['spec'].get('enforcementAction') != 'scoped'
                or not {'validation.gatekeeper.sh', 'audit.gatekeeper.sh'} <= points):
            raise RuntimeError('Unexpected Gatekeeper scope or enforcement mode')
        ns = {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'son-policy-test'}}
        if run(['apply', '-f', '-'], ns).returncode:
            raise RuntimeError('Could not prepare test namespace')
        for name, obj, policy, engine in cases(a.image):
            passed, _ = check(name, ['create', '--dry-run=server', '-f', '-', '-o', 'name'], obj, policy, engine)
            if name in {'pod-uid-nonroot', 'kyverno-valid'} and not passed:
                raise RuntimeError('Positive control failed; negative results would be ambiguous')
        suffix = str(time.time_ns())[-10:]
        name = 'integration-runtime-' + suffix
        obj = pod(name, a.image)
        ok, response = check('nonroot-pod-create', ['create', '-f', '-'], obj, engine='Gatekeeper', phase='actual-create')
        if not ok:
            raise RuntimeError('Runtime Pod admission failed')
        created.append(name)
        ok, _ = check('nonroot-pod-ready', ['-n', 'son-policy-test', 'wait', '--for=condition=Ready', 'pod/' + name, '--timeout=120s'], engine='kubelet', phase='runtime')
        if ok:
            ok_uid, uid = check('runtime-uid', ['-n', 'son-policy-test', 'exec', name, '--', 'id', '-u'], engine='container', phase='runtime')
            if not ok_uid or uid.stdout.strip() != '10001':
                results[-1]['result'] = 'FAIL'
            ok_http, http = check('runtime-http', ['-n', 'son-policy-test', 'exec', name, '--', 'wget', '-qO-', 'http://127.0.0.1:8080'], engine='container', phase='runtime')
            if not ok_http or http.stdout.strip() != 'team4 server ok':
                results[-1]['result'] = 'FAIL'
        ephemeral = {'spec': {'ephemeralContainers': [{'name': 'root-debug', 'image': a.image,
                      'command': ['id'], 'securityContext': {'runAsUser': 0}}]}}
        check('root-ephemeral-container', ['-n', 'son-policy-test', 'patch', 'pod', name,
              '--subresource=ephemeralcontainers', '--type=merge', '--dry-run=server', '-p', json.dumps(ephemeral)],
              policy='son-require-nonroot', engine='Gatekeeper')
        bad = pod('integration-rejected-' + suffix, a.image)
        bad['spec']['securityContext']['runAsUser'] = 0
        bad['spec']['containers'][0]['command'] = ['id']
        passed, response = check('root-actual-create-rejected', ['create', '-f', '-'], bad,
                                  policy='son-require-nonroot', engine='Gatekeeper', phase='actual-create')
        if response.returncode == 0:
            created.append(bad['metadata']['name'])
        snapshot = run(['-n', 'son-policy-test', 'get', 'pods', '-o', 'json'])
        if snapshot.returncode == 0 and any(x['metadata']['name'] == bad['metadata']['name'] for x in json.loads(snapshot.stdout)['items']):
            results[-1]['result'] = 'FAIL'
        for args in [['get', 'constrainttemplate', 'team4nonroot', '-o', 'json'],
                     ['get', 'team4nonroot', 'son-require-nonroot', '-o', 'json']]:
            response = run(args)
            if response.returncode == 0:
                statuses = json.loads(response.stdout).get('status', {})
                errors = [item.get('errors') for item in statuses.get('byPod', []) if item.get('errors')]
                errors += [point for item in statuses.get('byPod', []) for point in item.get('enforcementPointsStatus', [])
                           if point.get('state') == 'error']
                ready = bool(statuses.get('byPod'))
                if args[1] == 'constrainttemplate':
                    ready = ready and statuses.get('created') is True
                else:
                    ready = ready and all(p.get('enforced') is True for p in statuses['byPod'])
                results.append({'test': 'controller-status-' + args[1], 'phase': 'controller-status',
                                'result': 'PASS' if ready and not errors else 'FAIL', 'errors': errors,
                                'command_record': f'{counter:03d}-command.json'})
    except (RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
        results.append({'test': 'execution', 'phase': 'setup-or-runtime', 'result': 'FAIL', 'reason': str(exc)})
        print(str(exc), flush=True)
    finally:
        for name in created:
            run(['-n', 'son-policy-test', 'delete', 'pod', name, '--wait=false'])
        (a.output_dir / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    return 1 if not results or any(item['result'] != 'PASS' for item in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
