"""Son's internal risk model, fed by the integration's existing scanner artifacts.

Missing, stale, skipped, malformed or unproven scans never become a clean result.
No scanners, builds, AWS calls or legacy report generators are invoked here.
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


# Retained from Son's report. These are review hypotheses, not tool severities.
RULES = {
    'CKV_AWS_394': ('2.8.1', 2, 2, '가용영역 식별자 고정 검토'),
    'CKV_AWS_130': ('2.6.1', 3, 4, '퍼블릭 IP 자동 할당 필요성 검토'),
    'CKV_AWS_338': ('2.9.4', 3, 4, '로그 보존기간 검토'),
    'CKV_AWS_158': ('2.7.2', 3, 4, 'CloudWatch KMS 암호화 적용'),
    'CKV_AWS_39': ('2.6.1', 3, 5, 'EKS 엔드포인트 접근 범위 제한 검증'),
    'CKV_AWS_58': ('2.7.2', 3, 5, 'EKS Secrets 암호화 설정'),
    'CKV_AWS_37': ('2.9.4', 4, 4, 'EKS Control Plane 로그 활성화'),
    'CKV_AWS_136': ('2.7.2', 3, 4, 'ECR KMS 암호화 적용 검토'),
    'CKV2_AWS_12': ('2.6.1', 4, 5, '기본 보안 그룹 트래픽 제한 검증'),
    'CKV2_AWS_11': ('2.10.2', 3, 4, 'VPC Flow Logs 활성화 검토'),
    'CKV2_AWS_5': ('2.8.1', 2, 2, '보안 그룹 연결 여부 확인'),
}
SEVERITY_RISK = {'CRITICAL': (4, 5), 'HIGH': (3, 4), 'MEDIUM': (2, 3), 'LOW': (1, 2)}


def risk(likelihood=None, impact=None, basis='미평가: 담당자 검토 필요'):
    score = likelihood * impact if likelihood is not None and impact is not None else None
    return {'likelihood': likelihood, 'impact': impact, 'score': score,
            'grade': '미평가' if score is None else '상' if score >= 15 else '중' if score >= 8 else '하',
            'basis': basis}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def checkov_findings(data):
    reports = data if isinstance(data, list) else [data]
    if not reports:
        raise ValueError('empty Checkov report list')
    counts = Counter()
    findings, skipped = [], []
    for report in reports:
        summary, results = report['summary'], report['results']
        if report.get('check_type') != 'terraform':
            raise ValueError('expected Terraform Checkov report')
        for key in ['passed', 'failed', 'skipped', 'parsing_errors']:
            value = summary[key]
            if type(value) is not int or value < 0:
                raise ValueError(f'invalid Checkov count: {key}')
            counts[key] += value
        for key in ['passed', 'failed', 'skipped']:
            checks = results[key + '_checks']
            if not isinstance(checks, list) or len(checks) != summary[key]:
                raise ValueError(f'Checkov {key} summary/details mismatch')
        skipped.extend({'id': x['check_id'], 'resource': x.get('resource'),
                        'reason': x.get('check_result', {}).get('suppress_comment', '미확보')}
                       for x in results['skipped_checks'])
        for check in results['failed_checks']:
            rule = RULES.get(check['check_id'])
            controls, assessment, action = ['2.10.2', '2.11.2'], risk(), '신규 규칙의 통제항목·위험도 검토'
            if rule:
                control, likelihood, impact, action = rule
                controls = [control, '2.11.2']
                assessment = risk(likelihood, impact, '팀원 규칙별 초기 가정: ' + action + '; 실제 노출·보완통제 미평가')
            findings.append({'id': check['check_id'], 'name': check.get('check_name'),
                             'target': check.get('resource'), 'file': check.get('file_path'),
                             'lines': check.get('file_line_range'), 'tool_severity': check.get('severity') or 'NOT_PROVIDED',
                             'controls': controls, 'internal_risk': assessment, 'action': action,
                             'exception_approved': False})
    if counts['passed'] + counts['failed'] + counts['skipped'] == 0:
        raise ValueError('Checkov has no evaluated checks')
    return dict(counts), findings, skipped


def trivy_findings(data):
    if data.get('SchemaVersion') != 2 or data.get('ArtifactType') != 'container_image':
        raise ValueError('expected Trivy schema 2 container_image report')
    results = data['Results']
    if not isinstance(results, list) or not results:
        raise ValueError('Trivy has no scan results')
    os_info = data['Metadata']['OS']
    if not os_info.get('Family'):
        raise ValueError('Trivy OS coverage missing')
    packages = sum(len(result.get('Packages') or []) for result in results)
    if not packages:
        raise ValueError('Trivy package inventory missing; use --list-all-pkgs')
    counts, findings = Counter(), []
    for result in results:
        vulnerabilities = result.get('Vulnerabilities') or []
        if not isinstance(vulnerabilities, list):
            raise ValueError('invalid vulnerability list')
        for item in vulnerabilities:
            severity = item.get('Severity', 'UNKNOWN')
            counts[severity] += 1
            assessment = risk(*SEVERITY_RISK[severity], basis='도구 심각도 기반 팀 내부 초기 가정; 도달 가능성·악용 여부 미평가') if severity in SEVERITY_RISK else risk()
            findings.append({'id': item['VulnerabilityID'], 'name': item.get('Title'),
                             'target': result.get('Target'), 'package': item.get('PkgName'),
                             'installed_version': item.get('InstalledVersion'), 'fixed_version': item.get('FixedVersion'),
                             'tool_severity': severity, 'severity_source': item.get('SeveritySource'),
                             'controls': ['2.10.8', '2.11.2'], 'internal_risk': assessment,
                             'action': '수정 버전 및 애플리케이션 호환성 검토'})
    return {'packages': packages, 'findings': len(findings), 'by_severity': dict(counts),
            'high_critical': counts['HIGH'] + counts['CRITICAL'], 'os_eosl': os_info.get('EOSL', False)}, findings, []


def analyze(tool, path, metadata_path=None, expected_commit=None, expected_run=None):
    path = Path(path)
    record = {'tool': tool, 'path': str(path), 'state': 'MISSING', 'gate': 'UNKNOWN',
              'counts': None, 'findings': [], 'skipped_checks': [], 'issues': [], 'metadata': {}}
    meta_path = Path(metadata_path) if metadata_path else Path(str(path) + '.meta.json')
    if not path.is_file():
        try:
            meta = read_json(meta_path)
            if isinstance(meta, dict):
                record['metadata'] = meta
                if meta.get('status') in {'SKIPPED', 'NOT_RUN'}:
                    record['state'] = meta['status']
                elif meta.get('status') == 'ERROR' or (type(meta.get('exit_code')) is int and meta['exit_code'] != 0):
                    record['state'] = 'ERROR'
                elif meta.get('status') == 'RUNNING':
                    record['state'] = 'INCOMPLETE'
        except (OSError, ValueError):
            pass
        record['issues'].append('결과 파일 없음: 검사 완료 여부 미확보')
        return record
    record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        data = read_json(path)
        counts, findings, skipped = (checkov_findings if tool == 'checkov' else trivy_findings)(data)
        record.update(counts=counts, findings=findings, skipped_checks=skipped)
        if tool == 'trivy':
            metadata = data.get('Metadata', {})
            record['image'] = {'artifact_name': data.get('ArtifactName'), 'image_id': metadata.get('ImageID'),
                               'repo_digests': metadata.get('RepoDigests', []), 'artifact_id': data.get('ArtifactID'),
                               'report_created_at': data.get('CreatedAt'),
                               'image_created_at': metadata.get('ImageConfig', {}).get('created')}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        record.update(state='ERROR', counts=None)
        record['issues'].append('검사 JSON 구조/범위 확인 실패: ' + str(exc))
        return record
    record['state'] = 'UNVERIFIED'
    try:
        meta = read_json(meta_path)
        if not isinstance(meta, dict):
            raise ValueError('metadata must be an object')
        record['metadata'] = meta
    except (OSError, ValueError) as exc:
        record['issues'].append('검사 시각·종료 코드·커밋 증거 미확보: ' + str(exc))
        return record
    if meta.get('status') in {'SKIPPED', 'NOT_RUN'}:
        record.update(state=meta['status'], counts=None, findings=[], skipped_checks=[])
        record['issues'].append('검사 미실행/생략: 남아 있는 JSON은 이번 결과로 사용하지 않음')
        return record
    if tool == 'checkov' and not meta.get('tool_version'):
        reports = data if isinstance(data, list) else [data]
        versions = {r.get('summary', {}).get('checkov_version') for r in reports}
        if len(versions) == 1 and None not in versions:
            meta['tool_version'] = versions.pop()
            meta['version_source'] = 'report.summary.checkov_version (raw metadata unchanged)'
    required = ['started_at', 'finished_at', 'commit', 'target', 'tool_version', 'source_tree_sha256']
    for key in required:
        if not meta.get(key):
            record['issues'].append(key + ': 미확보')
    if meta.get('tool') != tool or meta.get('status') != 'FINISHED':
        record['issues'].append('도구 또는 실행 완료 상태 불일치')
    if meta.get('output_sha256') != record['sha256']:
        record['issues'].append('JSON 해시와 검사 메타데이터 불일치')
    if expected_commit and meta.get('commit') != expected_commit:
        record['issues'].append('요청한 커밋과 검사 커밋 불일치')
    if expected_run and str(meta.get('run_id')) != str(expected_run):
        record['issues'].append('요청한 실행 ID와 검사 실행 ID 불일치')
    if tool == 'trivy' and meta.get('image_config_digest') and meta['image_config_digest'] != record['image']['image_id']:
        record['issues'].append('스캔한 이미지와 기록된 config digest 불일치')
    if record['issues']:
        return record
    rc = meta.get('exit_code')
    if type(rc) is not int:
        record['issues'].append('종료 코드 미확보')
        return record
    if tool == 'checkov':
        operational_error = counts['parsing_errors'] > 0 or rc not in [0, 1] or (rc == 1 and counts['failed'] == 0)
        failed = counts['failed'] > 0
        incomplete = counts['skipped'] > 0
    else:
        # The complete Trivy JSON command runs with its default exit-code=0;
        # HIGH/CRITICAL gating consumes this same file after coverage validation.
        operational_error = rc != 0
        failed = counts['high_critical'] > 0 or counts['os_eosl']
        incomplete = False
    if operational_error:
        record.update(state='ERROR', gate='UNKNOWN')
        record['issues'].append('도구 실행 또는 파싱 실패: 취약점 없음으로 해석할 수 없음')
    else:
        record.update(state='PARTIAL' if incomplete else 'COMPLETE', gate='FAILED' if failed else 'UNKNOWN' if incomplete else 'PASSED')
        if incomplete:
            record['issues'].append('검사 생략 항목 존재: 전체 안전 판정 불가')
    return record


def build_report(checkov, trivy, commit=None, run_id=None):
    scans = [checkov, trivy]
    issues = []
    for key in ['commit', 'run_id', 'source_tree_sha256']:
        values = [scan['metadata'].get(key) for scan in scans]
        if all(values) and values[0] != values[1]:
            issues.append('검사 간 ' + key + ' 불일치: 서로 다른 결과를 하나의 실행으로 합산하지 않음')
    return {'generated_at': datetime.now(timezone.utc).isoformat(), 'requested_commit': commit,
            'run_id': run_id, 'status': 'INCOMPLETE' if issues or any(s['state'] != 'COMPLETE' for s in scans)
            else 'FINDINGS' if any(s['findings'] or s['gate'] == 'FAILED' for s in scans) else 'NO_FINDINGS_IN_SCANNED_SCOPE',
            'scope': '기술적 검사 증거와 팀 내부 위험도 가정. ISMS-P 인증 전체 충족 판정이 아님.',
            'scoring': '가능성(1~5) × 영향도(1~5); 상 15~25 / 중 8~14 / 하 1~7. 도구 심각도와 별개.',
            'mapping_basis': '팀원 규칙별 매핑과 policies/isms-p.json의 기술 통제 매핑; 담당자 적합성 검토 필요.',
            'issues': issues, 'scans': scans}


def escape(value):
    return str(value if value is not None else '미확보').replace('|', '\\|').replace('\n', ' ')


def markdown(report):
    lines = ['# 통합본 ISMS-P 기술 위험도 보고서', '', f"- 생성 시각: {report['generated_at']}",
             f"- 결과: **{report['status']}**", '- ' + report['scope'], '- ' + report['scoring'],
             '- ' + report['mapping_basis'], '', *['- ' + issue for issue in report['issues']]]
    for scan in report['scans']:
        meta = scan['metadata']
        lines += ['', f"## {scan['tool']}: {scan['state']} / gate={scan['gate']}", '',
                  f"- 원본: `{scan['path']}`; SHA256: `{scan.get('sha256', '미확보')}`",
                  f"- 검사 시작/종료: {meta.get('started_at', '미확보')} / {meta.get('finished_at', '미확보')}",
                  f"- 도구 버전: {escape(meta.get('tool_version'))}; 종료 코드: {escape(meta.get('exit_code'))}",
                  f"- 대상: {escape(meta.get('target'))}; 실행 ID: {escape(meta.get('run_id'))}",
                  f"- 커밋: {escape(meta.get('commit'))}; 미커밋 변경: {escape(meta.get('dirty'))}",
                  f"- 소스 트리 SHA256: {escape(meta.get('source_tree_sha256'))}",
                  f"- 이미지 정보: {escape(json.dumps(scan.get('image', {}), ensure_ascii=False))}; config digest: {escape(meta.get('image_config_digest'))}",
                  '- 수치: ' + (json.dumps(scan['counts'], ensure_ascii=False) if scan['counts'] is not None else '확보하지 못함 (0건 아님)'),
                  *['- 확인 필요: ' + issue for issue in scan['issues']], '',
                  '| ID / 항목 | 대상·버전 | 도구 심각도 | 내부 가능성×영향도=점수 / 등급 | ISMS-P | 산정 근거·조치 |',
                  '|---|---|---|---|---|---|']
        for finding in scan['findings']:
            r = finding['internal_risk']
            target = f"{finding.get('target')} {finding.get('file', '')} {finding.get('lines', '')} {finding.get('package', '')} {finding.get('installed_version', '')} → {finding.get('fixed_version', '')}"
            lines.append('| ' + ' | '.join(map(escape, [finding['id'] + ': ' + (finding.get('name') or ''), target,
                finding['tool_severity'], f"{r['likelihood']}×{r['impact']}={r['score']} / {r['grade']}",
                ', '.join(finding['controls']), r['basis'] + '; ' + finding['action']])) + ' |')
        if scan['skipped_checks']:
            lines += ['', '생략 항목 (통과로 계산하지 않음):', '']
            lines.extend('- ' + escape(json.dumps(item, ensure_ascii=False)) for item in scan['skipped_checks'])
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkov', type=Path, default=Path('evidence/ci/checkov.json'))
    p.add_argument('--trivy', type=Path, default=Path('evidence/image/trivy.json'))
    p.add_argument('--checkov-meta', type=Path)
    p.add_argument('--trivy-meta', type=Path)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--commit')
    p.add_argument('--run-id')
    a = p.parse_args()
    outputs = [a.output_dir / 'isms-p-risk-report.json', a.output_dir / 'isms-p-risk-report.md']
    if any(path.exists() for path in outputs):
        p.error('report already exists; use a fresh run directory to preserve history')
    scans = [analyze('checkov', a.checkov, a.checkov_meta, a.commit, a.run_id),
             analyze('trivy', a.trivy, a.trivy_meta, a.commit, a.run_id)]
    report = build_report(*scans, a.commit, a.run_id)
    a.output_dir.mkdir(parents=True, exist_ok=True)
    outputs[0].write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    outputs[1].write_text(markdown(report), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'scans': {s['tool']: s['state'] for s in scans}, 'output': str(a.output_dir)}))
    return 2 if report['status'] == 'INCOMPLETE' else 1 if report['status'] == 'FINDINGS' else 0


if __name__ == '__main__':
    raise SystemExit(main())
