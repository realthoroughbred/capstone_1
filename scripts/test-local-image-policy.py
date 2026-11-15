"""Local-only public-key Kyverno admission test using a disposable HTTP registry.

Requires kind-team4, Kyverno, Docker, PyYAML and the checked image archive. Keys
exist only in a temporary directory. Existing registry/namespace are never reused.
The ECR/OIDC policy is neither loaded nor modified by this test.
"""
import argparse
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

import yaml


def main():
    root = Path(__file__).absolute().parents[1]
    os.chdir(root)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=False)
    namespace, registry = 'son-kyverno-sign-test', 'team4-registry'
    k = ['kubectl', '--context', 'kind-team4']
    records, created, hosts = [], [], {}
    def run(cmd, *, data=None, check=True, private=False):
        # Docker Desktop may detach a WSL bind-mounted cwd after --rm exits.
        # Re-enter the stable repository path before launching relative tools.
        os.chdir(root)
        proc = subprocess.run(cmd, input=data, capture_output=True, text=True)
        os.chdir(root)
        if not private:
            number = len(records)
            (a.output_dir / f'{number:03}.stdout.txt').write_text(proc.stdout)
            (a.output_dir / f'{number:03}.stderr.txt').write_text(proc.stderr)
            records.append({'command': cmd, 'exit_code': proc.returncode,
                            'stdout': f'{number:03}.stdout.txt', 'stderr': f'{number:03}.stderr.txt'})
        if check and proc.returncode:
            raise RuntimeError(f'Command failed ({proc.returncode}): {cmd[:4]}')
        return proc
    def apply(document):
        return run(k + ['create', '-f', '-'], data=json.dumps(document))
    def pod(name, image):
        return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name, 'namespace': namespace},
                'spec': {'automountServiceAccountToken': False,
                         'securityContext': {'runAsNonRoot': True, 'runAsUser': 1000, 'seccompProfile': {'type': 'RuntimeDefault'}},
                         'containers': [{'name': 'app', 'image': image, 'imagePullPolicy': 'Always',
                         'securityContext': {'readOnlyRootFilesystem': True, 'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}}]}}
    outcome = {'evidence_kind': 'LOCAL', 'status': 'FAIL', 'tests': []}
    try:
        context = json.loads(run(k + ['config', 'view', '--minify', '-o', 'json']).stdout)
        if not context['clusters'][0]['cluster']['server'].startswith('https://127.0.0.1:'):
            raise RuntimeError('Only loopback kind-team4 is allowed')
        # Fail before creating anything if a previous registry or namespace exists.
        if run(['docker', 'inspect', registry], check=False).returncode == 0:
            raise RuntimeError('Existing registry must be reviewed, not overwritten')
        absent = run(k + ['get', 'namespace', namespace, '--ignore-not-found', '-o', 'name'])
        if absent.stdout.strip():
            raise RuntimeError('Existing test namespace must be reviewed')
        run(['docker', 'run', '-d', '--name', registry, '--network', 'kind', 'registry:2'])
        created.append('registry')
        ip = json.loads(run(['docker', 'inspect', registry]).stdout)[0]['NetworkSettings']['Networks']['kind']['IPAddress']
        apply({'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': namespace, 'labels': {'project': 'team4-local-signature'}}})
        created.append('namespace')
        apply({'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': registry, 'namespace': 'kyverno'},
               'spec': {'ports': [{'port': 5000, 'targetPort': 5000}]}})
        created.append('service')
        apply({'apiVersion': 'discovery.k8s.io/v1', 'kind': 'EndpointSlice',
               'metadata': {'name': registry, 'namespace': 'kyverno', 'labels': {'kubernetes.io/service-name': registry}},
               'addressType': 'IPv4', 'ports': [{'port': 5000, 'protocol': 'TCP'}],
               'endpoints': [{'addresses': [ip], 'conditions': {'ready': True}}]})
        created.append('endpoint')
        crane = ['docker', 'run', '--rm', '--network', 'kind', '-v', f'{a.archive.resolve()}:/image.tar:ro',
                 'gcr.io/go-containerregistry/crane:v0.20.3']
        for repo in ['signed', 'unsigned', 'wrong']:
            run(crane + ['push', '--insecure', '/image.tar', f'{registry}:5000/team4-{repo}:test'])
        digest = run(crane + ['digest', '--insecure', f'{registry}:5000/team4-signed:test']).stdout.strip()
        refs = {repo: f'{registry}:5000/team4-{repo}@{digest}' for repo in ['signed', 'unsigned', 'wrong']}
        with tempfile.TemporaryDirectory(prefix='team4-kyverno-keys-') as keydir:
            # Password is passed through the environment, never a command argument.
            previous = os.environ.get('COSIGN_PASSWORD')
            os.environ['COSIGN_PASSWORD'] = secrets.token_urlsafe(32)
            try:
                for name in ['good', 'wrong']:
                    run(['.tools/bin/cosign', 'generate-key-pair', '--output-key-prefix', f'{keydir}/{name}'], private=True)
                signer = ['docker', 'run', '--rm', '--network', 'kind', '-e', 'COSIGN_PASSWORD',
                          '-v', f'{keydir}:/keys:ro', '-v', f'{Path(".tools/bin/cosign").resolve()}:/usr/local/bin/cosign:ro',
                          'alpine:3.23.6', 'cosign']
                for name, repo in [('good', 'signed'), ('wrong', 'wrong')]:
                    run(signer + ['sign', '--yes', '--key', f'/keys/{name}.key', '--tlog-upload=false', '--allow-http-registry', refs[repo]])
                policy = yaml.safe_load(Path('policies/kyverno/local/verify-local-cosign.yaml').read_text())
                policy['spec']['attestors'][0]['cosign']['key']['data'] = Path(keydir, 'good.pub').read_text()
                (a.output_dir / 'policy-public-key.json').write_text(json.dumps(policy, indent=2))
                apply(policy)
            finally:
                if previous is None:
                    os.environ.pop('COSIGN_PASSWORD', None)
                else:
                    os.environ['COSIGN_PASSWORD'] = previous
        run(k + ['-n', namespace, 'wait', '--for=jsonpath={.status.conditionStatus.ready}=true', 'namespacedimagevalidatingpolicy/require-team4-cosign', '--timeout=180s'])
        run(k + ['-n', namespace, 'get', 'namespacedimagevalidatingpolicy/require-team4-cosign', '-o', 'json'])
        for name, expected in [('signed', True), ('unsigned', False), ('wrong', False)]:
            proc = run(k + ['create', '--dry-run=server', '-f', '-'], data=json.dumps(pod(name, refs[name])), check=False)
            success = proc.returncode == 0 if expected else proc.returncode != 0 and 'require-team4-cosign' in proc.stderr and 'Image must have' in proc.stderr
            outcome['tests'].append({'case': name, 'phase': 'SERVER_DRY_RUN', 'pass': success})
            if not success:
                raise RuntimeError(f'Unexpected policy decision for {name}')
        # Pull the same signed digest for a real Pod. Restore node registry config.
        nodes = run(['kind', 'get', 'nodes', '--name', 'team4']).stdout.split()
        path = '/etc/containerd/certs.d/team4-registry:5000/hosts.toml'
        for node in nodes:
            old = run(['docker', 'exec', node, 'cat', path], check=False)
            if old.returncode and 'No such file' not in old.stderr:
                raise RuntimeError('Cannot establish previous containerd configuration')
            hosts[node] = old.stdout if old.returncode == 0 else None
            run(['docker', 'exec', node, 'mkdir', '-p', '/etc/containerd/certs.d/team4-registry:5000'])
            run(['docker', 'exec', '-i', node, 'tee', path], data='server = "http://team4-registry:5000"\n[host."http://team4-registry:5000"]\n  capabilities = ["pull", "resolve"]\n')
        apply(pod('signed-runtime', refs['signed']))
        run(k + ['-n', namespace, 'wait', '--for=condition=Ready', 'pod/signed-runtime', '--timeout=180s'])
        live = json.loads(run(k + ['-n', namespace, 'get', 'pod', 'signed-runtime', '-o', 'json']).stdout)
        body = run(k + ['-n', namespace, 'exec', 'signed-runtime', '--', 'wget', '-qO-', 'http://127.0.0.1:8080']).stdout
        if body.strip() != 'team4 server ok' or not live['metadata']['uid'] or not live['status']['containerStatuses'][0]['imageID'].endswith(digest):
            raise RuntimeError('Pod identity/HTTP verification failed')
        outcome['tests'].append({'case': 'signed', 'phase': 'ACTUAL_POD_UID_DIGEST_HTTP', 'pass': True, 'uid': live['metadata']['uid'], 'image': refs['signed']})
        for name in ['unsigned', 'wrong']:
            proc = run(k + ['create', '-f', '-'], data=json.dumps(pod(name, refs[name])), check=False)
            if proc.returncode == 0 or 'require-team4-cosign' not in proc.stderr:
                raise RuntimeError(f'Actual invalid image not rejected: {name}')
            absent = run(k + ['-n', namespace, 'get', 'pod', name, '--ignore-not-found', '-o', 'name'])
            if absent.stdout.strip():
                raise RuntimeError('Rejected Pod exists')
            outcome['tests'].append({'case': name, 'phase': 'ACTUAL_REJECTION_AND_ABSENCE', 'pass': True})
        outcome['status'] = 'PASS'
    except Exception as exc:
        outcome['failure'] = str(exc)
    finally:
        try:
            if 'namespace' in created:
                run(k + ['delete', 'namespace', namespace, '--wait=true', '--timeout=90s'])
            for kind, flag in [('endpointslice', 'endpoint'), ('service', 'service')]:
                if flag in created:
                    run(k + ['-n', 'kyverno', 'delete', kind, registry])
            for node, original in hosts.items():
                path = '/etc/containerd/certs.d/team4-registry:5000/hosts.toml'
                if original is None:
                    run(['docker', 'exec', node, 'rm', '-f', path])
                else:
                    run(['docker', 'exec', '-i', node, 'tee', path], data=original)
            if 'registry' in created:
                run(['docker', 'rm', '-f', registry])
        except Exception as exc:
            outcome.update(status='FAIL', cleanup_failure=str(exc))
        (a.output_dir / 'commands.json').write_text(json.dumps(records, indent=2))
        (a.output_dir / 'results.json').write_text(json.dumps(outcome, indent=2))
        print(json.dumps(outcome, indent=2))
    return 0 if outcome['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
