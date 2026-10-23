"""Generate evidence reports, refusing PASS entries without existing evidence files."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RESULTS = {'PASS', 'FAIL', 'NOT_TESTED', 'BLOCKED'}
SCOPES = {'local', 'static', 'simulated', 'aws', 'github'}


def generate(mapping, observations, root):
    records = []
    for obs in observations:
        if obs['result'] not in RESULTS or obs['scope'] not in SCOPES:
            raise ValueError('invalid result/scope')
        policy = mapping['policies'][obs['policy_id']]
        evidence = []
        for name in obs.get('evidence', []):
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError(f'evidence missing or outside project: {name}')
            evidence.append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        if obs['result'] == 'PASS' and not evidence:
            raise ValueError('PASS requires evidence')
        record = dict(obs, policy_name=policy['name'], isms_p=[{'id': c, 'name': mapping['controls'][c]} for c in policy['controls']], evidence=evidence)
        for key, default in {'violations': [], 'remediation_executed': False, 'remediation_method': None,
                             'before': None, 'after': None, 'revalidation': 'NOT_TESTED', 'duration_seconds': None}.items():
            record.setdefault(key, default)
        records.append(record)
    return {'generated_at': datetime.now(timezone.utc).isoformat(), 'source': mapping['source'],
            'disclaimer': mapping['scope'], 'records': records}


def markdown(report):
    lines = ['# ISMS-P 기술 통제 증적', '', report['disclaimer'], '', f"공식 기준: {report['source']}", '']
    for item in report['records']:
        lines += [f"## {item['policy_id']} — {item['policy_name']}", '',
                  f"결과: **{item['result']}** · 검증 범위: **{item['scope']}**", '',
                  f"통제: {', '.join(c['id'] + ' ' + c['name'] for c in item['isms_p'])}", '',
                  '```json', json.dumps(item, ensure_ascii=False, indent=2), '```', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('observations', type=Path)
    parser.add_argument('--output', type=Path, default=Path('evidence/reports'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    report = generate(json.loads((root / 'policies/isms-p.json').read_text(encoding='utf-8')),
                      json.loads(args.observations.read_text(encoding='utf-8')), root)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'isms-p.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (args.output / 'isms-p.md').write_text(markdown(report), encoding='utf-8')
