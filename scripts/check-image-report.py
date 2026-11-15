"""Fail closed when a scanner reports no supported package inventory."""
import json
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from automation.scan_contract import validate_inventory


def validate(report):
    packages = validate_inventory(report)
    if report.get('Metadata', {}).get('OS', {}).get('EOSL'):
        raise ValueError('Unsupported/end-of-support base OS')
    return packages


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
