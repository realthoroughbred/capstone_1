"""Measure the entire violation -> detection -> verified recovery interval."""
import argparse
import json
from datetime import datetime
from pathlib import Path


def assess(record):
    result = {'status': 'NOT_TESTED', 'target_seconds': 1.0, 'evidence_kind': record.get('evidence_kind', 'UNSPECIFIED')}
    keys = ['violation_started_at', 'detected_at', 'recovery_verified_at']
    if not all(record.get(k) for k in keys):
        return {**result, 'reason': 'All three externally observed timestamps are required; Lambda duration is insufficient.'}
    values = [datetime.fromisoformat(record[k].replace('Z','+00:00')) for k in keys]
    if any(v.tzinfo is None for v in values) or not values[0] <= values[1] <= values[2]:
        raise ValueError('Invalid or out-of-order timestamps')
    elapsed = (values[2]-values[0]).total_seconds()
    return {**result, 'status': 'MEASURED', 'end_to_end_seconds': elapsed,
            'detection_seconds': (values[1]-values[0]).total_seconds(),
            'recovery_seconds': (values[2]-values[1]).total_seconds(),
            'target_met': elapsed <= 1.0, 'aws_target_proven': record.get('evidence_kind')=='AWS_LIVE' and elapsed<=1.0}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('timeline',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=assess(json.loads(a.timeline.read_text()))
    with a.output.open('x',encoding='utf-8') as out: json.dump(result,out,indent=2)
    print(json.dumps(result))
    raise SystemExit(2 if result['status']=='NOT_TESTED' else 0 if result['target_met'] else 1)
