"""Scan existing, image-bound SBOM bytes once. No image build and no AWS mutation."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from automation.sbom_watch import compare
from security_scan import source_identity
from verify_sbom_binding import verify_binding


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['sbom', 'binding', 'state', 'output-dir']:
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--artifact-commit', required=True)
    a = p.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', a.artifact_commit):
        p.error('artifact-commit must be a verified full commit')
    a.output_dir.mkdir(parents=True, exist_ok=False)
    a.state.parent.mkdir(parents=True, exist_ok=True)
    lock = Path(str(a.state) + '.lock')
    record = {'started_at': datetime.now(timezone.utc).isoformat(), 'source': source_identity(),
              'artifact_commit': a.artifact_commit, 'artifact_commit_verification': 'CALLER_PROVIDED; batch mode validates GitHub run head',
              'evidence_kind': 'LOCAL_SBOM_RESCAN', 'scan_exit_code': None}
    acquired = False
    rc = 2
    try:
        with lock.open('x'):
            acquired = True
        binding = json.loads(a.binding.read_text(encoding='utf-8'))
        verify_binding(a.sbom, a.binding, binding.get('image_config_digest'))
        # Config digests identify local artifacts. Registry manifests identify ECR images.
        digest = binding.get('registry_manifest_digest') or binding['image_config_digest']
        record.update(image_digest=digest, image_config_digest=binding['image_config_digest'],
                      registry_manifest_digest=binding.get('registry_manifest_digest'),
                      sbom_sha256=hashlib.sha256(a.sbom.read_bytes()).hexdigest())
        command = ['trivy', 'sbom', '--scanners', 'vuln', '--format', 'json', '--output', str(a.output_dir/'trivy.json'), str(a.sbom)]
        record['command'] = command
        with (a.output_dir/'scan-output.txt').open('wb') as output:
            response = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=600)
        record['scan_exit_code'] = response.returncode
        if response.returncode:
            raise ValueError('SBOM scanner failed; previous ledger retained')
        old = json.loads(a.state.read_text()) if a.state.exists() else {'schema_version': 1, 'images': {}}
        result = compare(json.loads((a.output_dir/'trivy.json').read_text()), digest, old)
        (a.output_dir/'ledger-before.json').write_text(json.dumps(old, indent=2)+'\n')
        (a.output_dir/'ledger-after.json').write_text(json.dumps(result['ledger'], indent=2)+'\n')
        temporary = Path(str(a.state) + '.new')
        temporary.write_text(json.dumps(result.pop('ledger'), indent=2)+'\n')
        os.replace(temporary, a.state)
        record.update(result)
        rc = 1 if result['deployment_gate'] == 'BLOCKED' else 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        record.update(status='INCOMPLETE', reason=str(exc), deployment_gate='UNKNOWN')
    finally:
        if acquired:
            lock.unlink(missing_ok=True)
        record.update(finished_at=datetime.now(timezone.utc).isoformat(), exit_code=rc)
        (a.output_dir/'result.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: record.get(k) for k in ['status', 'image_digest', 'deployment_gate', 'exit_code']}))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
