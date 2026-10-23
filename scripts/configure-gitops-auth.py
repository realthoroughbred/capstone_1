"""Create a read-only GitHub deploy key and load it directly into Argo CD.

Run with the existing authenticated Windows Git credential helper. Private key
material only lives in a temporary directory and the Kubernetes repository Secret.
"""
import argparse
import base64
import importlib.util
import json
import pathlib
import subprocess
import struct
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--repo', default='realthoroughbred/capstone_1')
parser.add_argument('--context', choices=['kind-team4', 'team4-eks'], required=True)
parser.add_argument('--wsl', action='store_true', help='Use kubectl in WSL Ubuntu; Git credentials remain on Windows')
parser.add_argument('--inspect-only', action='store_true', help='Read deploy-key metadata only; do not generate or create keys')
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('github_ci', pathlib.Path(__file__).with_name('github-ci.py'))
github = importlib.util.module_from_spec(spec)
spec.loader.exec_module(github)
try:
    deploy_keys = github.api(args.repo, '/keys?per_page=100')
except RuntimeError as error:
    parser.exit(1, str(error) + '\n')
key_metadata = [{key: item.get(key) for key in ('id', 'title', 'read_only', 'created_at', 'verified')}
                for item in deploy_keys]
print(json.dumps({'existing_deploy_keys': key_metadata}, indent=2))
if args.inspect_only:
    raise SystemExit(0)
kubectl = (['wsl', '-d', 'Ubuntu', '--', 'kubectl'] if args.wsl else ['kubectl']) + ['--context', args.context]
existing = subprocess.run(kubectl + ['-n', 'argocd', 'get', 'secret', 'team4-gitops-repository', '--ignore-not-found', '-o', 'name'], capture_output=True)
if existing.returncode:
    parser.exit(1, 'Could not check the Argo repository Secret; verify cluster access before creating a deploy key.\n')
if existing.stdout.strip():
    print('Argo repository secret already exists; keeping the existing deploy key.')
    raise SystemExit(0)
title = f'team4-argocd-{args.context}'
orphaned = [key['id'] for key in deploy_keys if key['title'] == title]
if orphaned:
    parser.exit(1, f'GitHub deploy key(s) {orphaned} already use {title}, but the Argo repository Secret is absent. '
                   'Inspect these keys in Settings > Deploy keys before authorizing cleanup; no new key created.\n')
key_id = None
with tempfile.TemporaryDirectory(prefix='team4-gitops-') as directory:
    private = pathlib.Path(directory) / 'id_ed25519'
    subprocess.run(['ssh-keygen', '-t', 'ed25519', '-N', '', '-C', f'team4-argocd-{args.context}', '-f', str(private)],
                   check=True, capture_output=True)
    public = private.with_suffix('.pub').read_text(encoding='ascii').strip()
    parts = public.split()
    if len(parts) < 2 or parts[0] != 'ssh-ed25519':
        parser.exit(1, 'Generated public key has an unexpected OpenSSH format; no GitHub write attempted.\n')
    try:
        wire = base64.b64decode(parts[1], validate=True)
        if (len(wire) != 51 or struct.unpack('>I', wire[:4])[0] != 11 or wire[4:15] != b'ssh-ed25519'
                or struct.unpack('>I', wire[15:19])[0] != 32):
            raise ValueError('Invalid ed25519 wire format')
    except (ValueError, struct.error):
        parser.exit(1, 'Generated public key failed format validation; no GitHub write attempted.\n')
    try:
        created = github.api(args.repo, '/keys', 'POST', {'title': title, 'key': public, 'read_only': True})
    except RuntimeError as error:
        parser.exit(1, str(error) + '\nNo retry attempted; inspect the validation error before creating another key.\n')
    key_id = created['id']
    secret = {'apiVersion': 'v1', 'kind': 'Secret',
              'metadata': {'name': 'team4-gitops-repository', 'namespace': 'argocd',
                           'labels': {'argocd.argoproj.io/secret-type': 'repository'},
                           'annotations': {'team4/github-deploy-key-id': str(key_id)}},
              'type': 'Opaque', 'stringData': {'type': 'git', 'url': f'git@github.com:{args.repo}.git',
                                              'sshPrivateKey': private.read_text()}}
    # Avoid kubectl client-side last-applied annotation duplicating private key.
    result = subprocess.run(kubectl + ['apply', '--server-side', '--field-manager=team4-gitops-auth', '-f', '-'],
                            input=json.dumps(secret), text=True, capture_output=True)
    if result.returncode:
        raise SystemExit(f'Argo Secret write failed; remove unused GitHub deploy key ID {key_id} from repository Settings > Deploy keys. Private key was not logged.')
print(f'Configured read-only deploy key {key_id}; repository URL git@github.com:{args.repo}.git')
