"""Fail closed when a scanner reports no supported package inventory."""
import json
import argparse
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


def enforce(report):
    validate(report)
    findings = [v for result in report.get('Results', []) for v in (result.get('Vulnerabilities') or [])
                if v.get('Severity') in {'HIGH', 'CRITICAL'}]
    for item in findings:
        print(item.get('VulnerabilityID'), item.get('PkgName'), item['Severity'])
    print(f'HIGH/CRITICAL findings: {len(findings)}')
    return 1 if findings else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--enforce-high-critical', action='store_true')
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    print('Verified package inventory:', validate(report))
    sys.exit(enforce(report) if args.enforce_high_critical else 0)
