"""Record a non-secret local validation command with its raw combined output."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('command required')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    record = {'command': command, 'cwd': str(Path.cwd()),
              'started_at': datetime.now(timezone.utc).isoformat()}
    print('Recording:', command, flush=True)
    rc = 127
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
    record.update(exit_code=rc, finished_at=datetime.now(timezone.utc).isoformat())
    (args.output_dir / 'command.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return rc if 0 <= rc <= 255 else 1


if __name__ == '__main__':
    raise SystemExit(main())
