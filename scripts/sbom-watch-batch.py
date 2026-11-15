"""Download approved immutable CI artifacts and scan their bound SBOMs; no AWS access."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=Path('config/sbom-watch.json'))
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--state-dir', required=True, type=Path)
    a = p.parse_args()
    config = json.loads(a.config.read_text())
    a.output_dir.mkdir(parents=True, exist_ok=False)
    if config.get('enabled') is not True or not config.get('targets'):
        (a.output_dir/'status.json').write_text(json.dumps({'status': 'NOT_TESTED', 'reason': 'No approved SBOM target configured'})+'\n')
        return 2
    repo = os.environ['GITHUB_REPOSITORY']
    if repo != 'realthoroughbred/capstone_1':
        raise ValueError('Unexpected artifact repository')
    codes = []
    for index, target in enumerate(config['targets']):
        run_id = str(target['run_id'])
        if not run_id.isdigit() or not re.fullmatch(r'[0-9a-f]{40}', target['commit']):
            raise ValueError('Invalid approved artifact provenance')
        metadata = json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/actions/runs/{run_id}']))
        if metadata['head_sha'] != target['commit'] or metadata['conclusion'] != 'success':
            raise ValueError('Artifact run is not a successful run of the approved commit')
        folder = a.output_dir/str(index)
        folder.mkdir()
        subprocess.run(['gh', 'run', 'download', run_id, '--repo', repo, '--name', 'deployment-evidence', '--dir', str(folder/'artifact')], check=True)
        binding = folder/'artifact/registry-binding.json'
        link = json.loads(binding.read_text())
        if link.get('registry_manifest_digest') != target['image_digest']:
            raise ValueError('Artifact image differs from approved manifest digest')
        code = subprocess.run([sys.executable, 'scripts/sbom-watch.py', '--sbom', str(folder/'artifact/image/sbom.cdx.json'),
            '--binding', str(binding), '--artifact-commit', target['commit'], '--state', str(a.state_dir/(target['image_digest'].replace(':', '-')+'.json')),
            '--output-dir', str(folder/'scan')]).returncode
        codes.append(code)
    return 2 if any(c not in [0, 1] for c in codes) else max(codes)


if __name__ == '__main__':
    raise SystemExit(main())
