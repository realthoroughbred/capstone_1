# 두 브랜치 통합본 로컬 시연

## 작업 범위와 보존 내역

통합 브랜치는 `codex/integrate-son-security`이다. 기준은 `codex/devsecops-self-healing`의
`4c6521503e1057d6289e7d71d45dae2511498e00`, 팀원 소스는
`feature/son-eks-security-automation`의 `edb7f4a11b70812e65a2fb7a41e9914905c197fa`이다.
두 원격 브랜치를 가져와 비교했으며 공통 조상이 없어서 파일별로 선별 통합했다.
작업 시작 시 Git 추적 파일의 미커밋 변경은 없었다. 기존 ignored 파일과 로컬 클러스터를 보존했다.
AWS 자원 조회·생성·변경·삭제, Terraform 실제 plan/apply/destroy, AWS 배포 workflow는 실행하지 않았다.

| 구성 | 통합 결정 |
|---|---|
| [Terraform](../infra/), [Dockerfile](../containers/test/Dockerfile), [Checkov 설정](../.checkov.yaml) | 기준 브랜치 그대로 유지. 팀원 파일로 교체하지 않음 |
| [AWS 배포 workflow](../.github/workflows/deploy.yml), [자동복구](../automation/) | OIDC·이미지 서명·SBOM 검증, Lambda/boto3 및 실행 안전 조건 유지 |
| [Kyverno](../policies/kyverno/), [NetworkPolicy](../policies/network/), [ESO·Argo CD 구성](../k8s/) | 기존 코드와 보안 통제 유지 |
| [Gatekeeper](../policies/gatekeeper/) | 팀원 Rego v1 로직 보존. 대상과 실행 위치를 명시하고 설치·실제 시험 추가 |
| [위험도 보고서](../scripts/07-isms-p-risk-report.py) | 팀원 점수 모델을 유지하며 실제 CI JSON, 실행 상태·시간·커밋·해시·이미지 정보 연결 |
| [기존 CI](../.github/workflows/checkov.yml) | 기존 두 검사 job 유지, 같은 실행의 artifact로 보고서 job 추가. 별도 팀원 Trivy workflow를 중복 추가하지 않음 |
| [이미지 검사](../scripts/image-security.sh) | 한 번의 전체 Trivy JSON을 심각도 게이트와 보고서가 공유. HIGH/CRITICAL 차단과 빈 패키지 목록 거부 유지 |
| [로컬 서명](../scripts/local-signature-test.sh) | 입력 archive 지정 지원. 개인키는 증거 폴더 밖 임시 경로에 만들고 시험 종료 후 제거 |
| [과거 이력](history/README.md) | 문서·정책·원본 생성기 16개를 원본 바이트 및 SHA256과 함께 보관. 과거 수치를 이번 결과에 사용하지 않음 |

추가·수정 파일 목록은 다음과 같다. 기존 보고서 원문 복사본은 이력 폴더의 manifest에 전부 나열했다.

- 정책: [nonroot-template.yaml](../policies/gatekeeper/nonroot-template.yaml), [nonroot-constraint.yaml](../policies/gatekeeper/nonroot-constraint.yaml), [local-values.yaml](../policies/gatekeeper/local-values.yaml).
- 보고서·증거: [07-isms-p-risk-report.py](../scripts/07-isms-p-risk-report.py), [security_scan.py](../scripts/security_scan.py), [record-command.py](../scripts/record-command.py).
- 기존 검사 연결: [checkov.yml](../.github/workflows/checkov.yml), [ci-check.sh](../scripts/ci-check.sh), [image-security.sh](../scripts/image-security.sh), [check-image-report.py](../scripts/check-image-report.py), [local-signature-test.sh](../scripts/local-signature-test.sh).
- 설치·시험: [install-gatekeeper-local.sh](../scripts/install-gatekeeper-local.sh), [test-gatekeeper-local.py](../scripts/test-gatekeeper-local.py), [test_admission_cases.py](../tests/test_admission_cases.py), [test_risk_report.py](../tests/test_risk_report.py), [test_security_scan.py](../tests/test_security_scan.py), [test_scan_coverage.py](../tests/test_scan_coverage.py).
- 도구·문서: [actionlint.yaml](../.github/actionlint.yaml), [줄바꿈 보존 설정](../.gitattributes), [README](../README.md), 이 문서, [이력 폴더](history/).

## 실행 위치와 준비

Windows에서 Docker Desktop을 실행한 뒤 **WSL Ubuntu 터미널**에서 아래 명령을 실행한다.
PowerShell에서 Bash 명령을 직접 붙여 넣지 않는다. 작업 디렉터리는 이 저장소 루트이다.

```bash
cd /mnt/d/Downloads/team4-startup-guide/team4-startup
git switch codex/integrate-son-security
source .venv-ci/bin/activate
export PATH="$PWD/.tools/bin:$PATH"
export SECURITY_RUN_ID="integration-$(date -u +%Y%m%dT%H%M%SZ)"
export RUN="evidence/$SECURITY_RUN_ID"
mkdir -p "$RUN"
docker version
kubectl config get-contexts
kubectl --context kind-team4 get nodes
```

이번 확인 환경은 Windows + WSL Ubuntu, Python 3.12.12, Docker Engine 28.5.2,
kind `team4` / Kubernetes 1.35.0이다. Windows Python 3.13.7에서도 보고서 회귀 테스트를 실행했다.
WSL의 기본 Kubernetes 컨텍스트가 `team4-eks`였으므로 모든 명령에 `--context kind-team4`를 명시했다.
설치·정책 시험 스크립트는 이 컨텍스트의 API 주소가 loopback인지 확인하고 다른 주소면 중단한다.

의존성이 없다면 [Python 준비](../scripts/bootstrap-python.sh), [기본 도구 준비](../scripts/01-install-tools.sh),
[보안 도구 준비](../scripts/install-security-tools.sh)를 먼저 확인한다. 새 로컬 클러스터는
[로컬 클러스터 스크립트](../scripts/02-local-cluster.sh)로 만들 수 있다. 기존 `team4`를 삭제하지 않는다.
Kyverno가 없다면 `bash scripts/07-install-security-addons.sh kind-team4 kyverno`로 기존 정책을 설치한다.

## 1. 정적 검사와 기존 기능 회귀 테스트

```bash
python scripts/record-command.py --output-dir "$RUN/static-run" -- \
  env CI_EVIDENCE_DIR="$RUN/ci" bash scripts/ci-check.sh
```

성공 기준은 unit 테스트 성공, Terraform fmt/validate 성공, mock 9개 성공, Checkov 종료 코드 0이다.
실제 AWS 호출을 검증하는 테스트가 아니라 fake client·mock provider 테스트이다.
Checkov의 `skipped`는 통과 수에 합치지 않는다. 이번 생략 23건의 주석과 사유는 그대로 유지했다.
원본 출력은 `$RUN/static-run/output.txt`, 명령·시간·종료 코드는 `command.json`,
Checkov JSON과 메타데이터는 `$RUN/ci/checkov.json` 및 `checkov.json.meta.json`에 남는다.

## 2. 이미지 빌드·취약점 검사·SBOM

```bash
# 이번 환경에서 기본 DB 미러 연결이 끊겨 공식 GHCR 경로로 재시도했다.
export TRIVY_DB_REPOSITORY=ghcr.io/aquasecurity/trivy-db:2
python scripts/record-command.py --output-dir "$RUN/image-run" -- \
  env EVIDENCE_DIR="$RUN/image" bash scripts/image-security.sh
```

예상 출력은 `team4 server ok`, 패키지 목록 확인, SBOM 스키마 검증 후 `PASS: build...`이다.
새 HIGH/CRITICAL이 발견되면 종료 코드는 1이어야 하며 다음 서명·Pod 시연으로 진행하지 않는다.
빈 스캔이나 오래된 지원 종료 OS도 성공으로 처리하지 않는다. MEDIUM/LOW/UNKNOWN은 보고서에 모두 남긴다.
DB 다운로드 실패 시 이전 JSON을 대신 쓰거나 DB 갱신을 끄지 않는다.

이번 최초 실행은 DB 미러 연결 오류로 실패했다. 재시도는 **이미 만든 동일 archive**를 사용했다.
빌드 없이 재시도하려면 새 하위 폴더를 지정한다.

```bash
mkdir -p "$RUN/image-retry"
python scripts/record-command.py --output-dir "$RUN/trivy-retry-run" -- \
  python scripts/security_scan.py --tool trivy --output "$RUN/image-retry/trivy.json" \
  --target team4-test:v1 --image-id-file "$RUN/image/image-config-digest.txt" -- \
  trivy image --input "$RUN/image/image.tar" --scanners vuln --list-all-pkgs \
  --db-repository ghcr.io/aquasecurity/trivy-db:2 --format json \
  --output "$RUN/image-retry/trivy.json"
python scripts/record-command.py --output-dir "$RUN/image-gate-retry-run" -- \
  python scripts/check-image-report.py "$RUN/image-retry/trivy.json" --enforce-high-critical
python scripts/record-command.py --output-dir "$RUN/sbom-run" -- \
  syft "docker-archive:$RUN/image/image.tar" -o "cyclonedx-json=$RUN/image-retry/sbom.cdx.json"
python scripts/record-command.py --output-dir "$RUN/sbom-validation-run" -- \
  python scripts/validate-sbom.py "$RUN/image-retry/sbom.cdx.json" \
  "$RUN/image/image-config-digest.txt" "$RUN/image-retry/sbom-link.json"
```

## 3. Gatekeeper 설치와 역할 분리

| 네임스페이스 | 담당 정책 | 역할 |
|---|---|---|
| `demo` | 기존 Kyverno `team4-restricted` | restricted PSS 및 모든 컨테이너의 읽기 전용 rootfs |
| `son-policy-test` | Gatekeeper `son-require-nonroot` | 일반·init·ephemeral 컨테이너의 유효 UID/NonRoot 조건 |
| 나머지 | 이 통합본 Gatekeeper 대상에 추가하지 않음 | 기존 시스템 및 다른 제어의 범위 유지 |

팀원의 namespace 전체 예외 실습은 [원본 이력](history/20261101-son-edb7f4a/docs/gatekeeper-nonroot-validation.md)에만 보존했다.
현재 설치는 예외 네임스페이스나 ignore 라벨을 만들지 않는다.
Gatekeeper webhook의 `failurePolicy: Fail`을 유지하며 Pod와 `pods/ephemeralcontainers`의 CREATE/UPDATE 요청 중
`son-policy-test`만 받는다. 이 제한으로 Calico IPAM 등 새 정책과 관계없는 시스템 요청이 설치를 막지 않게 했다.

```bash
GATEKEEPER_EVIDENCE_DIR="$RUN/gatekeeper" bash scripts/install-gatekeeper-local.sh
kubectl --context kind-team4 -n gatekeeper-system get pods
kubectl --context kind-team4 get constrainttemplate team4nonroot -o yaml
kubectl --context kind-team4 get team4nonroot son-require-nonroot -o yaml
```

Controller와 Audit 모두 `1/1 Running`이어야 한다. `status.byPod`의 관측 세대와 오류도 확인한다.
Rego 전용 정책을 CEL 전용 VAP에 전달하면서 발생하던 `K8sNativeValidation engine is missing`은
`scopedEnforcementActions`로 webhook·audit·gator의 `deny`를 명시하여 해결했다.
Rego 검사와 Audit은 계속 실행한다. 글로벌 CEL 엔진이나 기존 Kyverno를 끄지 않는다.
[Gatekeeper 공식 실행 위치 설명](https://open-policy-agent.github.io/gatekeeper/website/docs/enforcement-points/)과
[VAP 연동 설명](https://open-policy-agent.github.io/gatekeeper/website/docs/validating-admission-policy/)을 근거로 설정했다.

kind 노드가 이미지를 못 받거나 `content digest ... not found`가 발생하면 Docker 호스트에서 받아
해당 플랫폼만 export해서 전달한 후 새 로그 폴더로 설치를 재시도한다.

```bash
docker pull --platform linux/amd64 openpolicyagent/gatekeeper:v3.23.1
docker image save --platform linux/amd64 -o "$RUN/gatekeeper-amd64.tar" openpolicyagent/gatekeeper:v3.23.1
kind load image-archive "$RUN/gatekeeper-amd64.tar" --name team4
GATEKEEPER_EVIDENCE_DIR="$RUN/gatekeeper-retry" bash scripts/install-gatekeeper-local.sh
```

플랫폼 지정은 [Docker 공식 save 옵션](https://docs.docker.com/reference/cli/docker/image/save/)을 사용한다.
정책 엔진 버전은 3.23.1로 고정한다.

## 4. 서버 dry-run과 실제 Pod 실행을 나누어 시험

2단계 이미지 게이트가 성공한 동일 이미지를 사용한다.

```bash
IMAGE_ID="$(docker image inspect team4-test:v1 --format '{{.Id}}')"
POLICY_TEST_IMAGE="team4-test:integration-${IMAGE_ID#sha256:}"
docker tag team4-test:v1 "$POLICY_TEST_IMAGE"
docker image save --platform linux/amd64 -o "$RUN/test-image-amd64.tar" "$POLICY_TEST_IMAGE"
kind load image-archive "$RUN/test-image-amd64.tar" --name team4
python scripts/record-command.py --output-dir "$RUN/admission-run" -- \
  python scripts/test-gatekeeper-local.py --output-dir "$RUN/admission" --image "$POLICY_TEST_IMAGE"
```

허용 대조군이 먼저 통과해야 거부 결과를 인정한다. 단순 연결 실패는 정책 차단으로 세지 않는다.
거부 응답에는 아래 정책 이름이 실제로 포함되어야 한다.

| 사례 | 검사 방식 | 기대 결과/판정 주체 |
|---|---|---|
| UID 10001, UID 없이 `runAsNonRoot: true` | 서버 dry-run | Gatekeeper 대상에서 허용 |
| UID 0, UID/NonRoot 모두 없음 | 서버 dry-run | `son-require-nonroot`가 거부 |
| 컨테이너 UID 0이 Pod UID를 덮어씀, NonRoot false가 Pod 플래그를 덮어씀 | 서버 dry-run | `son-require-nonroot`가 거부 |
| 컨테이너 UID 10001이 Pod UID 0을 덮어씀 | 서버 dry-run | 허용 |
| init·두 번째 일반 컨테이너·ephemeral 컨테이너의 UID 0 | 서버 dry-run | `son-require-nonroot`가 거부 |
| `demo` 정상 Pod / root Pod / 쓰기 가능한 rootfs | 서버 dry-run | 허용 / `team4-restricted` 거부 / `team4-restricted` 거부 |
| `son-policy-test`의 쓰기 가능한 rootfs | 서버 dry-run만 | NonRoot 규칙만 평가하므로 허용. 실행하거나 운영 예외로 삼지 않음 |
| 정상 NonRoot Pod | 실제 생성 및 실행 | 생성 → Ready → `id -u`가 `10001` → HTTP `team4 server ok` |
| root Pod | 실제 생성 요청 | Gatekeeper가 거부, Pod가 목록에 생기지 않음 |

UID 없는 NonRoot 플래그 사례의 컨테이너 실행은 이번에 별도로 검증하지 않았다.
실제 실행 증거는 명시적 UID 10001 사례에 해당한다. 테스트는 자기 실행에서 만든 Pod만 정리한다.
모든 요청 JSON, 명령, 종료 코드와 stdout/stderr는 `$RUN/admission/NNN-command.json`,
판정은 `results.json`에 기록한다.

## 5. 기존 로컬 서명 검증

```bash
python scripts/record-command.py --output-dir "$RUN/signature-run" -- \
  env EVIDENCE_DIR="$RUN/signature" IMAGE_ARCHIVE="$PWD/$RUN/image/image.tar" \
  bash scripts/local-signature-test.sh
```

정상 공개키 검증은 성공하고 다른 키는 `no matching signatures`와 `invalid signature`로 실패해야 한다.
별도 Docker 네트워크의 임시 레지스트리를 사용하며 종료 후 정리한다.
로컬 시험의 HTTP/tlog 생략은 기존 실습 범위이다. AWS의 OIDC/keyless/tlog 검증 성공으로 확대 해석하지 않는다.
개인키와 비밀번호는 증거에 저장하지 않는다. 공개 검증 응답은 `$RUN/signature/verify.json`에 남는다.

## 6. 기존 검사 결과로 보고서 생성

최초 이미지 검사가 성공했다면 `TRIVY_RESULT="$RUN/image/trivy.json"`, 재시도했다면 아래 경로를 사용한다.

```bash
TRIVY_RESULT="$RUN/image-retry/trivy.json"
python scripts/record-command.py --output-dir "$RUN/report-run" -- \
  python scripts/07-isms-p-risk-report.py \
  --checkov "$RUN/ci/checkov.json" --trivy "$TRIVY_RESULT" \
  --output-dir "$RUN/report" --commit "$(git rev-parse HEAD)" --run-id "$SECURITY_RUN_ID"
```

보고서 JSON/Markdown은 지정한 폴더에만 쓴다. 기존 결과가 있으면 새 실행 폴더를 요구한다.
경로가 다른 sidecar는 `--checkov-meta`, `--trivy-meta`로 지정할 수 있다.
종료 코드는 0=검증된 검사 범위에서 발견 없음, 1=발견 항목 있음, 2=검사 생략·실패·누락·증거 불일치 등 불완전이다.
HIGH/CRITICAL 게이트 통과와 전체 취약점 없음은 다르다. MEDIUM·LOW·UNKNOWN도 보고서 발견 항목으로 남는다.

메타데이터의 실행 시각, 대상, 커밋, dirty 상태, 작업 트리 SHA256, 결과 SHA256, 도구 버전과 종료 코드를 사용한다.
Trivy는 이미지 config digest와 스캔 ImageID도 대조한다. registry digest가 없는 로컬 archive는 미확보로 표시한다.
위험도 점수는 팀 내부 초기 가정 `가능성 × 영향도`이며, 도구의 심각도와 별도 열이다.
알 수 없는 규칙이나 UNKNOWN 심각도에는 점수를 만들어 넣지 않는다. 관련 ISMS-P 통제번호는 기술 증거 매핑이며 인증 전체 충족 판정이 아니다.

CI에서는 `validate`의 `evidence/ci/checkov.json`과 `image`의 `evidence/image/trivy.json`을
`static-and-unit-evidence`, `image-security-evidence` artifact에서 다운로드한다.
여러 경로를 올리는 이미지 artifact의 루트는 `evidence/`이므로 `image/` 하위 구조를 그대로 복원한다.
보고서 job은 실패한 검사 뒤에도 실행하고, 파일이 없으면 불완전 보고서를 남긴다.
artifact 다운로드 단계의 오류 허용은 증거 누락 보고를 위한 것이며 검사 job과 보안 게이트에는 적용하지 않는다.
현재처럼 생략 항목이 있으면 보고서 job이 종료 코드 2를 낼 수 있다. 결과를 초록색으로 만들기 위한 자동 예외 승인은 하지 않는다.

## 이번 실제 실행 기록과 남은 확인

현재 증거 루트는 [evidence/integration-20261101](../evidence/integration-20261101/)이다.
이 폴더는 Git 제외 대상이며 원본 로그·검사 JSON을 로컬에서 열 수 있다.
과거 root 보고서 생성기를 실행하지 않았고, Git 이력의 보고서 숫자를 복사하지 않았다.

| 실제 실행 | 확인 결과 | 원본 경로 (증거 루트 기준) |
|---|---|---|
| 환경 | Docker 시작 전 중지 상태 확인, 기존 kind 두 노드 Ready, EKS 컨텍스트 미사용 | `01-environment.txt`, `02-host-runtime.txt`, `04-local-cluster.txt` |
| 기존 및 통합 단위 테스트 | 최종 131개 통과. VS Code 미탐색으로 저장소의 unittest 명령 사용 | `final-unit-run/output.txt`, `final-unit-run/command.json` |
| 셸·CI 문법 | 셸 문법 및 actionlint 1.7.7 성공. 기존 self-hosted runner 라벨만 설정에 등록 | `shell-syntax-run/command.json`, `workflow-lint-final-run/command.json` |
| Terraform | fmt/validate 성공, mock 9개 성공 | `ci/terraform-validate.json`, `ci/terraform-mock-tests.txt` |
| Checkov | 164 통과 / 0 실패 / 23 생략 / 파싱 오류 0 | `final-snapshot/ci/checkov.json`, `final-snapshot/ci/checkov.json.meta.json` |
| Trivy | 패키지 17개, 발견 3개: MEDIUM 1 + UNKNOWN 2, HIGH/CRITICAL 0 | `final-snapshot/image/trivy.json`, `final-snapshot/trivy-run/command.json` |
| SBOM | CycloneDX 1.7 스키마 및 config digest 연결, 구성요소 100개 | `image-retry/sbom-link.json`, `sbom-validation-run/command.json` |
| 로컬 서명 | 정상키 검증 및 다른 키 거부 성공 | `signature-run/output.txt`, `signature/verify.json`, `signature/wrong-key.txt` |
| Gatekeeper·Kyverno | 21개 판정 통과: 서버 dry-run 14, 실제 생성 요청 2, 실제 실행 확인 3, controller 상태 2 | `admission-retry/results.json`, `admission-retry-run/output.txt` |
| Gatekeeper Audit | 실행 시각 2026-11-01T08:38:18Z, 세대 2 적용, 해당 시점 위반 0, Native engine 오류 해소 | `admission-retry/028-command.json` |
| 이력·기존 소스 보존 | 원본 16개 바이트/SHA256 일치, 기존 인프라·Dockerfile·배포·자동복구·Kubernetes 파일 차이 없음 | `09-preservation-check.txt` |
| 통합 보고서 | `INCOMPLETE`: Checkov 23건 생략을 안전 판정으로 바꾸지 않음. 최종 검사 간 소스 SHA는 일치 | `final-snapshot/report/isms-p-risk-report.json`, `final-snapshot/report-run/command.json` |

초기 Checkov 실행 중 Gatekeeper 설치 수정이 있었고, Trivy 재시도 전 보고서 기록기를 고쳤다.
초기 `reviewed-report/`는 소스 SHA 차이를 불완전 사유로 명시했다. 최종 코드를 고정한 뒤
`integration-20261101-final` 실행에서 스캐너 두 개만 재실행해 입력 시점을 맞췄다. 이미지 빌드는 반복하지 않았다.
두 최종 메타데이터의 작업 트리 SHA256은 `b4ac94b3795a42d46c05c13297bb9651cf72873e9ec66a2192f424e44cb7dd6d`로 같다.
검사 커밋은 기준 커밋 `4c6521503e1057d6289e7d71d45dae2511498e00`, 통합 변경은 `dirty=true`로 명시한다.
최종 검사 후에는 이 안내의 결과·경로만 갱신했다. 각 스캐너의 시간·커밋·원본 결과는 변경하지 않았다.

실패/수정 이력도 남겼다: `gatekeeper/`는 첫 설치의 CNI 교착, `gatekeeper-retry/`는 이미지 다운로드 실패,
`gatekeeper-kind-load/`는 다중 플랫폼 로딩 실패, `gatekeeper-final/`은 설치 성공이다.
`image/trivy.json.stderr.txt`는 DB 미러 오류, `image-retry/`는 공식 GHCR 재시도 결과이다.
첫 `admission/` 시험의 정상 Kyverno 입력은 테스트 객체 공유 때문에 잘못 변경되었다. deep copy로 수정했으며
원본 실패를 보존하고 `admission-retry/`에서 재시험하여 21개 모두 통과했다. 정책을 완화하지 않았다.
임시 재시도 shell을 실행 중 편집하여 상위 shell의 종료 오류가 발생한 기록도 있으며,
스캔·SBOM 개별 `command.json`의 종료 코드로 각 검사의 성공 여부를 구분한다.
actionlint의 최초 Docker 실행은 자격증명 helper 오류로 실패했다. 공식 release binary를 체크섬 확인 후 사용했으며,
기존 `team4-deploy` 사용자 정의 라벨을 [설정](../.github/actionlint.yaml)에 등록한 뒤 두 workflow가 검사에 통과했다.

GitHub Actions 원격 실행은 이번에 하지 않았다. 통합 브랜치 검토·푸시 후 새 run의 세 artifact와 job 결과를 확인해야 한다.
로컬 ESO secret rotation, NetworkPolicy 실제 트래픽 차단, Argo CD drift 복구 전체 시나리오는 이번에 재실행하지 않았다.
해당 소스는 보존했고 기동 상태를 확인했지만 과거 성공을 이번 성공으로 재사용하지 않는다.
[기존 Kubernetes 시연 안내](kubernetes-notes.md)의 **kind-team4** 절차로 추가 검증할 수 있다.
gator CLI, native CEL VAP 자체 검증도 수행하지 않았다. 이번 정책은 Rego webhook·Audit 경로이다.

AWS 단계에는 별도 실행 승인을 받은 뒤 다음을 넘긴다: 현재 IAM/권한 경계 및 자원 상태 재확인,
EKS용 네임스페이스·RBAC·Gatekeeper 가용성 설계, Kyverno와의 범위 검토, ECR OIDC/keyless 서명·SBOM·미서명 거부,
ESO Secrets Manager 회전, NetworkPolicy 트래픽, Argo CD drift, Config/EventBridge/Lambda 및 Inspector/CodeBuild 실이벤트 검증.
23개 Checkov 생략 사유와 Trivy MEDIUM/UNKNOWN 항목도 운영 맥락에서 검토해야 한다.
이번 로컬 결과는 AWS 운영 성공이나 ISMS-P 인증 적합성의 증거가 아니다.
