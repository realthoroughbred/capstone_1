"""Derive project status from retained command results; missing proof never becomes PASS."""
import argparse
import importlib.util
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--as-of', type=date.fromisoformat,
                    default=datetime.now(timezone(timedelta(hours=9))).date(),
                    help='Report review date in Asia/Seoul; does not change evidence timestamps.')
args = parser.parse_args()


def read(path):
    target = ROOT / path
    return target.read_text(encoding='utf-8', errors='replace') if target.is_file() else ''


def data(path):
    try:
        return json.loads(read(path))
    except (ValueError, TypeError):
        return {}


rows = []
observations = []


def record(name, policy, scope, passed, paths, detail, blocked=False, failed=False):
    status = 'PASS' if passed else ('BLOCKED' if blocked else ('FAIL' if failed else 'NOT_TESTED'))
    existing = [p for p in paths if (ROOT / p).is_file()]
    rows.append({'feature': name, 'scope': scope, 'result': status, 'detail': detail, 'evidence': existing})
    observations.append({'policy_id': policy, 'target': name, 'tool': name, 'scope': scope,
                         'result': status, 'details': detail, 'evidence': existing})


validation = data('evidence/terraform/validate.json')
record('Terraform validate', 'IAC-001', 'static', validation.get('valid') is True,
       ['evidence/terraform/validate.json', 'evidence/terraform/fmt.txt'], 'Provider 스키마 검증. 실제 AWS plan/apply와 구분.')
mock = read('evidence/terraform/mock-tests.txt')
record('Terraform 안전 조건', 'IAC-001', 'simulated', bool(re.search(r'Success! \d+ passed, 0 failed', mock)),
       ['evidence/terraform/mock-tests.txt'], 'mock provider: 기본 dry run, 공개 CIDR 금지, OIDC subject, 서명 전용 태그 예외.')
scan = data('evidence/terraform/checkov.json').get('summary', {})
record('Checkov', 'IAC-001', 'static', bool(scan) and scan.get('failed') == 0 and scan.get('parsing_errors') == 0,
       ['evidence/terraform/checkov.json'], f"passed={scan.get('passed')}, failed={scan.get('failed')}, skipped={scan.get('skipped')}; 예외는 docs/infra-notes.md.")
unit = read('evidence/local/unit-tests.txt')
count = re.search(r'Ran (\d+) tests?', unit)
record('자동복구 단위·통합 테스트', 'NET-001', 'simulated', '\nOK' in unit and 'FAILED' not in unit,
       ['evidence/local/unit-tests.txt'], f"{count.group(1) if count else '?'}개 fake-client/로컬 테스트. 실제 Config/Inspector 이벤트 아님.")
record('Docker HTTP', 'OPS-001', 'local', read('evidence/image/http-response.txt').strip() == 'team4 server ok',
       ['evidence/image/http-response.txt', 'evidence/image/image-inspect.json'], '비 root·읽기전용 rootfs·cap drop 환경에서 TCP8080 응답.')
trivy = data('evidence/image/trivy.json')
packages = sum(len(r.get('Packages', [])) for r in trivy.get('Results', []))
bad = [v for r in trivy.get('Results', []) for v in r.get('Vulnerabilities', []) if v.get('Severity') in {'HIGH', 'CRITICAL'}]
record('Trivy 정상 이미지', 'IMG-001', 'local', packages > 0 and not bad and 'PASS: build' in read('evidence/local/image-security.txt'),
       ['evidence/image/trivy.json', 'evidence/image/trivy-gate.txt'], f'실제 탐지 패키지 {packages}개, HIGH/CRITICAL {len(bad)}개. 미탐지 목록은 통과시키지 않음.')
positive = data('evidence/vulnerable-control/gate.json')
record('Trivy 취약 이미지 거부', 'IMG-001', 'local', positive.get('result') == 'PASS',
       ['evidence/vulnerable-control/gate.json', 'evidence/vulnerable-control/trivy.json'],
       f"검사 전용 alpine:3.12.0, HIGH/CRITICAL {positive.get('high_critical_count', '?')}건, 실제 프로세스 종료코드1. 실행·배포하지 않음.")
sbom = data('evidence/image/sbom-link.json')
record('CycloneDX SBOM', 'IMG-001', 'local', bool(sbom.get('component_count')),
       ['evidence/image/sbom.cdx.json', 'evidence/image/sbom-link.json'],
       f"CycloneDX {sbom.get('schema_version')}, 구성요소 {sbom.get('component_count')}개. 공식 스키마 검사 및 실제 config digest 연결.")
signature = data('evidence/local-signature/verify.json')
wrong = read('evidence/local-signature/wrong-key.txt')
record('cosign 로컬 서명', 'IMG-002', 'local', isinstance(signature, list) and bool(signature) and 'no matching signatures' in wrong,
       ['evidence/local-signature/verify.json', 'evidence/local-signature/wrong-key.txt', 'evidence/local-signature/signed-image.txt'],
       '실제 OCI 레지스트리 서명·정상키 검증·다른키 거부. 테스트 키/tlog 비활성. AWS OIDC/keyless 검증 아님.')
record('NetworkPolicy', 'NET-002', 'local', 'PASS: NetworkPolicy enforcement' in read('evidence/network-kind-team4.log'),
       ['evidence/network-kind-team4.log', 'evidence/network-kind-team4.json'], '실제 DNS, client→server, 독립 ingress/egress 차단 및 양방향 허용 대조군.')
record('ESO Fake/rotation', 'SEC-001', 'local', 'PASS: Rotation reached' in read('evidence/eso-kind-team4.log'),
       ['evidence/eso-kind-team4.log'], 'Kubernetes Secret와 실행중 Pod 볼륨의 값 변화 확인. 원문 출력 없음. AWS SM 검증 아님.')
admission = data('evidence/admission-kind-team4.json')
required_admission = {'valid-security-context', 'root-user', 'privileged', 'privilege-escalation', 'writable-root-filesystem'}
passed_admission = {r.get('test') for r in admission if r.get('result') == 'PASS'} if isinstance(admission, list) else set()
record('Kyverno admission', 'IMG-002', 'local', required_admission <= passed_admission,
       ['evidence/admission-kind-team4.json', 'evidence/admission-kind-team4.log'], '정상 Pod 허용 및 잘못된 보안 컨텍스트의 실제 webhook 거부. ECR 서명 정책은 별도 검증 필요.')
gitops = data('evidence/gitops-kind-team4.json')
record('Argo CD GitOps 복구', 'NET-002', 'local', gitops.get('result') == 'PASS',
       ['evidence/gitops-kind-team4.json', 'evidence/gitops-kind-team4.log'], 'Git commit 기준 drift 감지→컨트롤러 복구→통신 재검증. admission과 구분.')
events = {item['event']: item for item in gitops.get('events', [])}
restored = events.get('AUTOMATIC_RESTORE_VERIFIED', {})
if restored:
    observations[-1].update({
        'violations': ['demo/allow-client-to-server ingress removed by the local test'],
        'remediation_executed': True, 'remediation_method': 'Argo CD automated selfHeal from the pinned local Git mirror',
        'before': events.get('DRIFT_ADMITTED', {}).get('spec'), 'after': restored.get('restored_spec'),
        'revalidation': 'PASS' if gitops.get('result') == 'PASS' else 'FAIL',
        'duration_seconds': restored.get('elapsed_seconds'), 'source_commit': gitops.get('revision')})
runs = data('evidence/github/runs.json')
ci_pass = isinstance(runs, list) and bool(runs) and all(r.get('conclusion') == 'success' for r in runs)
ci_paths = ['evidence/github/runs.json']
ci_detail = '실제 원격 커밋의 실행 결과. 로컬 스크립트 실행을 CI 성공으로 대체하지 않음.'
if isinstance(runs, list) and runs:
    snapshot = f"evidence/github/runs-{runs[0].get('head_sha')}.json"
    if (ROOT / snapshot).is_file():
        ci_paths = [snapshot]
    ci_detail += f" 커밋 `{runs[0].get('head_sha', '')}` · [실행]({runs[0].get('url', '')})."
record('GitHub Actions CI', 'OPS-001', 'github', ci_pass,
       ci_paths, ci_detail,
       failed=isinstance(runs, list) and any(r.get('conclusion') in {'failure', 'timed_out', 'action_required'} for r in runs))
preflight = data('evidence/aws/preflight.json')
auth_blocked = preflight.get('authentication', {}).get('result') == 'BLOCKED'
inventory_checks = preflight.get('checks', [])
inventory_ready = (not auth_blocked and
                   {c.get('name') for c in inventory_checks} ==
                   {'eks', 'project_vpcs', 'config_recorders', 'ecr', 'oidc_providers'} and
                   all(c.get('result') == 'PASS' for c in inventory_checks))
inventory_detail = ('현재 AWS 인증 확인 실패. 최신 조회·권한 확인을 수행하지 못함.' if auth_blocked else
                    'STS 및 EKS·VPC·ECR·Config·OIDC 읽기 전용 조회.')
inventory_detail += f" 마지막 확인: {preflight.get('timestamp', '기록 없음')}."
record('AWS 신원·기존 자원 조회', 'OPS-001', 'aws', inventory_ready,
       ['evidence/aws/preflight.json'], inventory_detail,
       blocked=not inventory_ready)
aws_plan = data('evidence/aws/plan-summary.json')
plan_ready = aws_plan.get('result') == 'PASS' and aws_plan.get('read_only') is True
record('AWS Terraform plan', 'IAC-001', 'aws', plan_ready,
       ['evidence/aws/plan-summary.json', 'evidence/aws/demo-plan.txt'],
       f"보관된 실제 AWS provider 계획: {aws_plan.get('actions', {})}. apply 미실행. 현재 입력·자원 상태로 새 plan을 확인한 뒤 실행해야 함. docs/AWS_PLAN_REVIEW.md 참고.")
authorization = data('evidence/aws/authorization.json')
authorized = authorization.get('resource_creation') is True and authorization.get('cleanup_after_validation_new_resources_only') is True
reason = ('team4 AWS 로그인 세션 만료. aws login으로 재인증 후 IAM·기존 자원·최신 plan을 재확인해야 함. AWS 작업은 실행하지 않음.'
          if auth_blocked and preflight['authentication'].get('reason') == 'SessionExpired' else
          'AWS 인증/계정 확인 실패. 승인 계정의 로그인 복구 후 권한·기존 자원을 다시 확인해야 함.' if auth_blocked else
          '신규 생성·최대 8시간 검증·DemoOnly SG 시험·검증 후 신규 자원 정리 승인 완료. 마지막 권한 검사에서 VPC 생성 DryRun 거부와 runtime boundary 부재가 확인됐으므로 관리자 IAM 준비 상태를 다시 확인해야 함.' if authorized and plan_ready else
          '실제 plan 완료. 정확한 범위의 배포 IAM 준비 및 유료 생성 승인 대기.' if plan_ready else
          '사전 조회 완료. 실제 plan·정확한 범위의 배포 IAM 준비 및 유료 생성 승인이 필요함.' if inventory_ready else
          'team4 프로필 인증됨. 자원 조회 IAM 권한 부족 및 유료 생성 승인 전.' if preflight else 'AWS 계정 사전 점검 필요.')
record('AWS plan/ECR/EKS/Config/Inspector', 'NET-001', 'aws', False,
       ['evidence/aws/preflight.json', 'evidence/aws/deployment-permissions.json', 'evidence/aws/authorization.json'], reason, blocked=True)
github_readiness = data('evidence/github/deployment-readiness.json')
if github_readiness:
    readiness_checks = github_readiness.get('checks', {})
    environment = readiness_checks.get('deployment_environment', {}).get('summary', {})
    runners = readiness_checks.get('runners', {}).get('summary', {})
    # Prerequisite observations are not proof of deployment or permission readiness.
    ready_detail = (f"확인 {github_readiness.get('timestamp')}: aws-demo 환경 조회 "
                    f"{'성공' if environment.get('exists') else '미확인'}, "
                    f"사용 가능한 전용 runner {runners.get('eligible_online_count', '미확인')}개. "
                    'main에 검토한 배포 workflow 반영·환경 보호 설정·AWS 역할 연결 후 실검증 필요.')
    record('GitHub AWS 배포 준비', 'OPS-001', 'github', False,
           ['evidence/github/deployment-readiness.json'], ready_detail, blocked=True)

mapping = data('policies/isms-p.json')
spec = importlib.util.spec_from_file_location('report', ROOT / 'scripts/evidence_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
report = reporter.generate(mapping, observations, ROOT)
(ROOT / 'evidence/reports').mkdir(parents=True, exist_ok=True)
(ROOT / 'evidence/reports/isms-p.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'evidence/observations.json').write_text(json.dumps(observations, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'ISMSP_MAPPING_REPORT.md').write_text(reporter.markdown(report), encoding='utf-8')

table = '| 기능 | 결과 | 검증 범위 | 증거/제한 |\n|---|---|---|---|\n'
for row in rows:
    table += f"| {row['feature']} | {row['result']} | {row['scope']} | {row['detail']} |\n"
intro = (f'작성 기준일 {args.as_of.isoformat()} (Asia/Seoul). `scripts/generate-project-reports.py`가 보관된 증적에서 생성합니다. '
         '작성일이 모든 항목의 재검증일을 뜻하지 않으며, 과거 로컬·모의·plan 성공은 현재 AWS 배포 성공과 구분합니다.\n\n')
status_table = '| 기능 | 구현 상태 | 검증 결과/범위 |\n|---|---|---|\n'
for row in rows:
    state = {'PASS': 'VERIFIED', 'BLOCKED': 'BLOCKED', 'FAIL': 'FAILED'}.get(row['result'], 'UNVERIFIED')
    status_table += f"| {row['feature']} | {state} | {row['result']} / {row['scope']} |\n"
(ROOT / 'IMPLEMENTATION_STATUS.md').write_text('# 구현 및 실검증 현황\n\n' + intro + status_table + '\nVERIFIED는 표의 범위만 의미합니다. 모의 API 테스트를 AWS 검증으로 계산하지 않습니다.\n\n' +
    '원본 GitHub main `98850606f7294d4885d97e2891e5535461dbb548`, Checkov feature `9950466a91f773fea1dba8c58b2c5b65b0fe8481`을 비교했습니다. 원래 압축 해제 폴더에 원본 이력을 연결하고 `codex/devsecops-self-healing`에서 작업합니다. Terraform state·인증정보는 업로드하지 않습니다.\n', encoding='utf-8')
(ROOT / 'SECURITY_TEST_REPORT.md').write_text('# 보안 시험 결과\n\n' + intro + table + '\n## 수정한 실제 실패\n\n' +
    '- 원본 bare BusyBox 이미지에 Trivy 패키지 인벤토리가 없어 탐지 누락이 발생했습니다. BusyBox httpd는 유지하고 Alpine APK 메타데이터를 추가했습니다. 원본 결과는 `evidence/busybox-baseline/`에 남겼습니다.\n' +
    '- Docker Desktop containerd의 image-store ID가 config digest와 달라, archive의 실제 config 바이트를 해시하도록 수정했습니다. ECR manifest.config.digest도 업로드 후 대조합니다.\n' +
    '- WSL/Desktop loopback 차이를 해결하기 위해 로컬 서명 시험은 같은 격리 네트워크 네임스페이스의 registry를 사용합니다. AWS 배포는 TLS와 OIDC/tlog 검증을 유지합니다.\n' +
    '- CycloneDX 사이트의 HTTP403을 피해 공식 GitHub 스키마를 검증된 commit으로 고정했습니다.\n' +
    '- Kyverno CRD가 지원하는 PodSecurity 버전과 Kubernetes 버전을 구분합니다.\n\n실제 명령과 증적 파일은 `docs/kubernetes-notes.md`, `docs/infra-notes.md`, `evidence/`에서 확인합니다.\n', encoding='utf-8')
remaining = '# 남은 작업\n\n' + intro
for row in rows:
    if row['result'] != 'PASS':
        remaining += f"- **{row['feature']} — {row['result']}**: {row['detail']}\n"
remaining += ('\nAWS 실행 순서: 로그인 갱신 → 관리자 배포 IAM 준비 확인 → 기존 state/자원 확인 → 최신 Terraform plan·비용을 기존 승인 범위와 대조 → apply → ECR 서명·EKS 배포 → SM rotation/서명 정책 → Config 실복구 → 증적 보존 → 이번 신규 자원 정리. Inspector는 별도 범위이며 안전 digest와 연결 가능한 CodeBuild가 준비되어야 합니다.\n\n'
    '총예산 상한은 사용자 지정 **180,000원**입니다. 예산은 자원 생성 승인과 별개이며 자동 종료를 보장하지 않습니다. 자세한 절차는 `AWS_DEPLOYMENT_GUIDE.md`, `COST_AND_CLEANUP.md`, `docs/TEAM4_IAM_PERMISSIONS.md`를 참고합니다.\n')
if authorized:
    remaining += '\n현재 사용자는 신규 생성·최대 8시간 검증·DemoOnly SG 시험·검증 후 신규 자원 정리를 승인했습니다. 같은 범위의 재승인 대신 관리자 IAM 준비 후 실행하며 기존 자원은 변경하지 않습니다.\n'
(ROOT / 'REMAINING_TASKS.md').write_text(remaining, encoding='utf-8')
readme = '''# AWS EKS DevSecOps + ISMS-P Self-Healing

BusyBox HTTP 테스트 프로그램을 사용해 이미지 검사·서명, Kubernetes 접근통제, AWS 설정 자동복구와 기술 통제 증적을 연결합니다. 실제 검증 범위는 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)에 구분했습니다. AWS 실행 상태와 남은 조건은 [남은 작업](REMAINING_TASKS.md)을 따릅니다.

```mermaid
flowchart LR
  Git --> CI[Terraform / Checkov / Trivy / Syft]
  CI --> Sign[cosign + SBOM attestation]
  Sign --> ECR --> EKS[Kyverno / NetworkPolicy / ESO]
  Config[AWS Config] --> EB[EventBridge] --> SG[Guarded Lambda SG recovery]
  Inspector --> EB2[EventBridge] --> Lambda[Approved digest check]
  Lambda --> Build[Trusted CodeBuild] --> EKS
  Git --> Argo[Argo CD NetworkPolicy recovery] --> EKS
  CI --> Evidence[JSON + Markdown ISMS-P evidence]
  SG --> Evidence
  EKS --> Evidence
```

## 실행 환경과 설치

Windows PowerShell에서 Ubuntu WSL 및 Docker Desktop을 사용합니다. 아래 명령은 Ubuntu의 프로젝트 루트에서 실행합니다. 기존 `kind-team4`는 재사용하며 삭제하지 않습니다.

```bash
bash scripts/01-install-tools.sh  # 기존 기본 도구가 없는 Linux x86_64 환경에서만
bash scripts/bootstrap-python.sh
source .venv-ci/bin/activate
export PATH="$PWD/.tools/bin:$PATH"
bash scripts/install-security-tools.sh
```

## 로컬 실행과 검증

```bash
bash scripts/02-local-cluster.sh  # 기존 team4가 있으면 재생성하지 않음
bash scripts/image-security.sh
bash scripts/03-local-workloads.sh
bash scripts/08-network-policy-test.sh kind-team4
bash scripts/09-eso-test.sh kind-team4 fake
bash scripts/07-install-security-addons.sh kind-team4 kyverno
bash scripts/10-admission-test.sh kind-team4
bash scripts/local-signature-test.sh
bash scripts/test-vulnerability-gate.sh
bash infra/validate-local.sh
bash infra/scan-security.sh
python scripts/generate-project-reports.py
```

GitOps 설정과 실제 drift 시험은 [Kubernetes 실행 안내](docs/kubernetes-notes.md)를 따릅니다. 이 저장소는 deploy key를 금지하므로 직접 연결에는 승인된 읽기 전용 GitHub 인증이 필요합니다. 로컬 시험은 게시된 40자리 commit의 읽기 전용 내부 mirror를 사용할 수 있습니다. 로컬 cosign 키 검증과 AWS keyless admission 검증은 별개입니다.

bare BusyBox 원본은 APK/DPKG 목록이 없어 취약점 검사 범위가 비어 있었습니다. 현재 Dockerfile은 Alpine에서 제공하는 BusyBox httpd를 사용하며, 패키지 목록이 없는 스캔과 빈 SBOM을 실패시킵니다. 이미지 config digest, registry manifest digest, Docker image-store ID를 구분합니다.

## AWS 배포

[실제 AWS 계획](docs/AWS_PLAN_REVIEW.md), [배포 가이드](AWS_DEPLOYMENT_GUIDE.md), [IAM 권한](docs/TEAM4_IAM_PERMISSIONS.md), [GitHub 설정](docs/GITHUB_SETUP.md), [비용·정리](COST_AND_CLEANUP.md)를 확인합니다. `team4` 프로필/계정 `852093844554`/서울 리전, 총예산 상한 180,000원입니다. 실제 plan을 검토하고 유료 생성 승인을 받은 뒤 배포합니다. 자동복구는 기본 DRY_RUN이며 운영 자원은 대상으로 삼지 않습니다.

CI는 PR에서 실행되고 AWS 배포는 보호된 `aws-demo` 환경의 main 전용 수동 workflow와 EKS에 접근 가능한 전용 runner에서 실행됩니다. NAT·ALB는 기본 구성에 없습니다. Inspector CodeBuild는 네트워크 경로가 준비된 별도 전용 프로젝트를 요구합니다.

## 문서·증적

- [보안 시험](SECURITY_TEST_REPORT.md), [자동복구](SELF_HEALING_REPORT.md), [ISMS-P 매핑](ISMSP_MAPPING_REPORT.md), [남은 작업](REMAINING_TASKS.md)
- [Terraform 설계와 Checkov 예외](docs/infra-notes.md), [자동복구 내부 계약](automation/README.md)
- 실제 JSON/명령 결과: `evidence/` (Git 제외). JSON 보고서: `evidence/reports/isms-p.json`.
- 기존 시작 안내서는 [docs/BOOTSTRAP_ORIGINAL.md](docs/BOOTSTRAP_ORIGINAL.md)에 보존했습니다. 현재 실행 절차는 이 README와 위 문서를 사용합니다.

기술 점검만으로 ISMS-P 전체 인증 충족 여부를 판단하지 않습니다. 로그·state·비밀키·AWS 자격증명을 Git에 올리지 않습니다.
'''
(ROOT / 'README.md').write_text(readme.replace('## AWS 배포\n\n', '## AWS 배포\n\n현재 실행 조건: ' + reason + '\n\n'), encoding='utf-8')
print(table)
