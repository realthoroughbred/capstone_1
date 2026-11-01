"""Capture one scanner invocation and its provenance, without changing its exit code.

Only pass non-secret scanner arguments. No environment, kubeconfig or credentials
are collected. The JSON report, stdout and stderr belong to a fresh run directory.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def source_identity():
    root = Path(git('rev-parse', '--show-toplevel'))
    names = subprocess.check_output(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=root
    ).decode().split('\0')
    digest = hashlib.sha256()
    for name in sorted(set(filter(None, names))):
        path = root / name
        digest.update(name.encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest() if path.is_file() else b'DELETED')
    return {'commit': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'),
            'dirty': bool(git('status', '--porcelain')), 'source_tree_sha256': digest.hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tool', choices=['checkov', 'trivy'], required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--target', required=True)
    p.add_argument('--run-id', default=os.environ.get('SECURITY_RUN_ID') or os.environ.get('GITHUB_RUN_ID'))
    p.add_argument('--image-id-file', type=Path)
    p.add_argument('--stdout-json', action='store_true')
    p.add_argument('command', nargs=argparse.REMAINDER)
    a = p.parse_args()
    command = a.command[1:] if a.command[:1] == ['--'] else a.command
    if not command:
        p.error('scanner command required after --')
    meta_path = Path(str(a.output) + '.meta.json')
    stdout_path = Path(str(a.output) + '.stdout.txt')
    stderr_path = Path(str(a.output) + '.stderr.txt')
    if any(path.exists() for path in [a.output, meta_path, stdout_path, stderr_path]):
        p.error('output already exists; choose a fresh evidence run directory')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    meta = {**source_identity(), 'schema_version': 1, 'tool': a.tool,
            'started_at': now(), 'finished_at': None, 'target': a.target,
            'run_id': a.run_id, 'command': command, 'status': 'RUNNING',
            'exit_code': None, 'cwd': str(Path.cwd())}
    if a.image_id_file and a.image_id_file.is_file():
        meta['image_config_digest'] = a.image_id_file.read_text().strip()
    meta_path.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    meta['tool_version'] = None
    rc = 127
    try:
        with (a.output if a.stdout_json else stdout_path).open('wb') as out, stderr_path.open('wb') as err:
            rc = subprocess.run(command, stdout=out, stderr=err).returncode
        meta['status'] = 'FINISHED'
    except OSError as exc:
        stderr_path.write_text(str(exc) + '\n', encoding='utf-8')
        meta['status'] = 'ERROR'
    finally:
        meta.update(exit_code=rc, finished_at=now())
        if a.output.is_file():
            meta['output_sha256'] = hashlib.sha256(a.output.read_bytes()).hexdigest()
        if a.tool == 'checkov' and a.output.is_file():
            # Checkov embeds its running version in the result. Avoid a second,
            # expensive cold Python import merely to call --version on WSL.
            try:
                document = json.loads(a.output.read_text(encoding='utf-8'))
                reports = document if isinstance(document, list) else [document]
                versions = {r['summary']['checkov_version'] for r in reports}
                if len(versions) == 1:
                    meta['tool_version'] = versions.pop()
                    meta['version_source'] = 'report.summary.checkov_version'
            except (ValueError, KeyError, TypeError):
                pass
        elif a.tool == 'trivy':
            try:
                version = subprocess.run([command[0], '--version'], capture_output=True, text=True, timeout=30)
                meta['tool_version'] = version.stdout.strip() if version.returncode == 0 else None
            except (OSError, subprocess.TimeoutExpired):
                pass
        meta_path.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    print(f'{a.tool}: exit={rc}, result={a.output}, metadata={meta_path}')
    return rc if 0 <= rc <= 255 else 1


if __name__ == '__main__':
    sys.exit(main())
