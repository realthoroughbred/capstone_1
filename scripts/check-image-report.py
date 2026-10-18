"""Fail closed when a scanner reports no supported package inventory."""
import json
import sys
from pathlib import Path


def validate(report):
    results = report.get('Results', [])
    packages = [p for result in results for p in result.get('Packages', [])]
    if not report.get('Metadata', {}).get('OS', {}).get('Family') or not packages:
        raise ValueError('Scanner coverage missing: no supported OS/package inventory')
    if report.get('Metadata', {}).get('OS', {}).get('EOSL'):
        raise ValueError('Unsupported/end-of-support base OS')
    return len(packages)


if __name__ == '__main__':
    print('Verified package inventory:', validate(json.loads(Path(sys.argv[1]).read_text())))
