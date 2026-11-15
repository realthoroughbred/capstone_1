"""Record a non-secret local validation command with its raw combined output."""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from security_scan import source_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--kind', choices=['LOCAL', 'MOCK', 'AWS_READ_ONLY', 'AWS_LIVE'], default='LOCAL')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('command required')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    # Console encoding must never interrupt collection of the original bytes.
    sys.stdout.reconfigure(errors='replace')
    record = {'command': command, 'cwd': str(Path.cwd()), 'evidence_kind': args.kind,
              'source_before': source_identity(),
              'started_at': datetime.now(timezone.utc).isoformat()}
    print('Recording:', command, flush=True)
    rc = 127
    try:
        with (args.output_dir / 'output.txt').open('wb') as log:
            try:
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                for line in proc.stdout:
                    log.write(line)
                    log.flush()
                    print(line.decode('utf-8', errors='replace'), end='', flush=True)
                rc = proc.wait()
            except OSError as exc:
                log.write((str(exc) + '\n').encode())
    finally:
        os.chdir(record['cwd'])
        record.update(exit_code=rc, finished_at=datetime.now(timezone.utc).isoformat(),
                      source_after=source_identity())
        (args.output_dir / 'command.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return rc if 0 <= rc <= 255 else 1


if __name__ == '__main__':
    raise SystemExit(main())
