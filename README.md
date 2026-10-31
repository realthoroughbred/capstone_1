## Gatekeeper를 이용한 Root 사용자 실행 차단

Kubernetes의 Pod 생성 요청에서 실행 사용자 ID를 검사합니다.
컨테이너 또는 Pod에 지정된 유효 runAsUser가 1 이상이어야 허용하며,
UID가 0이거나 설정이 없으면 요청을 거부합니다.

### 검증 환경
- 로컬 kind 클러스터: team4
- kubectl 컨텍스트: kind-team4
- Gatekeeper 버전: v3.23.1
- 적용 대상: son-policy-test 네임스페이스의 Pod
- AWS EKS 검증은 아직 진행하지 않았습니다.

### 정책 파일
- `policies/gatekeeper/nonroot-template.yaml`: 사용자 ID를 검사하는 Rego 정책
- `policies/gatekeeper/nonroot-constraint.yaml`: 검사 범위와 차단 모드 설정

컨테이너의 runAsUser를 우선 사용하고, 없으면 Pod의 값을 사용합니다.

### 적용 방법
Gatekeeper가 설치된 kind-team4 환경에서 실행합니다.

```bash
kubectl --context kind-team4 create namespace son-policy-test \
  --dry-run=client -o yaml | kubectl --context kind-team4 apply -f -

kubectl --context kind-team4 apply \
  -f policies/gatekeeper/nonroot-template.yaml

kubectl --context kind-team4 get crd \
  team4nonroot.constraints.gatekeeper.sh
```

CRD가 조회되는 것을 확인한 뒤 제약 조건을 적용합니다.
아직 조회되지 않으면 잠시 후 다시 확인합니다.

```bash
kubectl --context kind-team4 apply \
  -f policies/gatekeeper/nonroot-constraint.yaml
```

### 검증 결과
서버 dry-run으로 실제 Pod를 생성하지 않고 생성 요청을 검사했습니다.

| 설정 | 확인 결과 |
| --- | --- |
| Pod runAsUser: 0 | Gatekeeper가 생성 요청 거부 |
| Pod runAsUser: 1000, runAsNonRoot: true | 생성 요청 허용 |

Root 설정의 요청에서는 다음 차단 메시지를 확인했습니다.

```text
[son-require-nonroot] Container test must set runAsUser >= 1 at Pod or container level
```

### 검증 범위
- 로컬 환경에서 생성 요청의 차단과 허용을 확인했습니다.
- 실제 컨테이너 실행은 검증하지 않았습니다.
- UID 미설정과 컨테이너별 UID 재정의 등은 추가 시험이 필요합니다.
- 기존 Pod를 자동 수정하거나 이전 상태로 복구하는 기능은 아닙니다.

<!-- son-security-status:start -->
## 담당 보안 자동화: 구현 내용 및 로컬 검증 현황

> **기준일:** 2026-11-01 · **작업 브랜치:** `feature/son-eks-security-automation`
> **검증 범위:** WSL Ubuntu + Docker Desktop + kind(`team4`)
> **배포 방침:** AWS 비용을 피하기 위해 로컬에서 먼저 검증하고 EKS 적용은 마지막에 별도로 진행합니다. **현재 EKS에 적용·검증한 결과가 아닙니다.**

### 처음 읽는 팀원을 위한 요약

이 프로젝트는 인프라 코드 작성부터 컨테이너 배포까지 서로 다른 위험을 단계별로 확인합니다. **Checkov**는 Terraform 설정을, **Trivy**는 이미지의 알려진 취약점을, **Gatekeeper**는 Kubernetes의 실행 정책을 검사합니다. **cosign**은 신뢰하는 키로 서명된 이미지인지 검증합니다. **ISMS-P 보고서**는 검사 결과를 통제항목·위험도·조치 방안과 연결합니다.

| 단계 | 무엇을 확인하나? | 도구/결과물 | 현재 상태 |
|---|---|---|---|
| 인프라 코드 검토 | AWS 보안 설정 오류 | Checkov | 로컬 실행 완료, 실패 12건 검토 중 |
| 이미지 취약점 검사 | HIGH/CRITICAL 취약점 | Trivy | 로컬 테스트 이미지 0건, Trivy CI 실행 성공 확인 |
| 배포 정책 검사 | Root 실행 등 정책 위반 | OPA Gatekeeper | 로컬 kind 입장 제어 검증 완료 |
| 이미지 출처·무결성 검증 | 지정 공개키로 서명을 검증할 수 있는가? | Sigstore/cosign | 로컬 서명·검증 자동화 성공 |
| 결과 관리 | 어떤 위험을 우선 조치할 것인가? | ISMS-P 위험도 보고서 | 자동 생성 및 조치 검토 문서 작성 완료 |

### 1. ISMS-P 매핑 확정 및 Checkov 룰셋 설정

- **목적:** 기술적 보안 요구사항을 프로젝트의 ISMS-P 통제항목에 연결하고, Terraform 코드에 일관된 검사 기준을 적용합니다.
- **구현:** `.checkov.yaml`에서 `infra/` 경로와 Terraform 프레임워크를 지정하고 `soft-fail: false`로 위반 발견 시 검사가 실패하도록 설정했습니다.
- **주요 매핑 예:** 보안 요구사항(2.8.1), 보안 테스트(2.8.2), 취약점 점검·조치(2.11.2), 권한·암호화·네트워크 등 관련 통제항목.
- **파일:** `.checkov.yaml`, `docs/isms-p-checkov-report.md`, `docs/isms-p-risk-report.md`.
- **주의:** 통제번호 매핑은 프로젝트 내부 기준이며, 이것만으로 ISMS-P 인증 요건 전체를 충족했다는 의미는 아닙니다. 초기 Checkov 보고서의 이전 수치 대신 아래 최신 로컬 검사 수치를 확인하세요.

### 2. Terraform IaC 정적 취약점 스캔 자동화

- **목적:** AWS에 자원을 생성하기 전에 잘못된 Terraform 보안 설정을 발견합니다.
- **구현:** `.github/workflows/checkov.yml`에서 GitHub Actions의 Checkov 검사를 설정했고, 현재 통합 작업 브랜치의 Push 및 PR에 맞게 구성했습니다.
- **로컬 결과:** Checkov `3.3.29`, 총 49건 중 **통과 37건 / 실패 12건**(검사 규칙 11종).
- **주요 검토 대상:** 퍼블릭 서브넷, EKS 퍼블릭 API, CloudWatch 보존·암호화, EKS 로그, VPC Flow Logs, 기본 보안 그룹 등.
- **CI 해석:** 위반 12건이 남아 있어 보안 게이트가 실패할 수 있습니다. **Checkov 실행 성공**과 **모든 보안 규칙 통과**는 다릅니다. CI를 초록색으로 만들기 위해 규칙 전체를 무력화하지 않습니다.
- **관련 파일:** `.github/workflows/checkov.yml`, `docs/checkov-findings-review.md`.

### 3. OPA Gatekeeper 설치 및 제약 조건 정의

- **목적:** Kubernetes API가 Pod 생성 요청을 받아들이기 전에 보안 정책을 검사합니다.
- **로컬 환경:** kind 클러스터 `team4`에 Gatekeeper Controller/Audit가 실행 중인 것을 확인했습니다. **설치 재현 자동화나 EKS 설치까지 완료했다는 뜻은 아닙니다.**
- **정책 구성:** `ConstraintTemplate` `team4nonroot`는 검사 로직(Rego)을, `Constraint` `son-require-nonroot`는 `deny` 모드와 대상 Namespace·Pod를 정의합니다.
- **파일:** `policies/gatekeeper/nonroot-template.yaml`, `policies/gatekeeper/nonroot-constraint.yaml`.
- **상태 확인:** `kubectl --context kind-team4 get pods -n gatekeeper-system` 및 `kubectl --context kind-team4 get team4nonroot son-require-nonroot`.

### 4. Root 권한 실행 방지 Rego 정책 적용

- **목적:** 명시적인 UID 0 또는 필요한 NonRoot 설정이 없는 Pod의 생성을 차단합니다.
- **구현:** Pod·컨테이너 수준의 `securityContext`에서 `runAsUser`와 `runAsNonRoot`를 평가합니다. 일반 컨테이너뿐 아니라 init/ephemeral 컨테이너도 검사하도록 작성했습니다.
- **로컬 검증 (서버 측 Dry Run):** `runAsUser: 0` 차단, `runAsUser: 1000` 허용, 보안 설정 없음 차단.
- **주의:** Kubernetes 입장 허용은 실제 컨테이너 실행 성공을 보장하지 않습니다. 이미지의 실제 실행 UID와 런타임 정책도 별도로 확인해야 합니다.

### 5. ISMS-P 위험도 평가 자동화 리포트 작성

- **목적:** Checkov와 Trivy의 검사 결과를 통합해 ISMS-P 통제항목, 위험도, 개선 방안을 기록합니다.
- **구현:** `scripts/07-isms-p-risk-report.py`가 `reports/checkov.json`을 읽어 실패 항목별 통제번호와 초기 위험점수(발생 가능성 1~5 × 영향도 1~5)를 계산하고, `reports/trivy.json`의 HIGH/CRITICAL 결과를 함께 기록합니다.
- **위험등급 기준(프로젝트 내부 초기값):** 상 15~25점, 중 8~14점, 하 1~7점.
- **현재 결과:** Checkov 실패 **12건** → 위험도 **상 4건 / 중 6건 / 하 2건**. Alpine 3.22 기반 로컬 테스트 이미지의 Trivy HIGH/CRITICAL **0건**.
- **파일:** `scripts/07-isms-p-risk-report.py`, `docs/isms-p-risk-report.md`, `docs/checkov-findings-review.md`.
- **한계:** 점수는 검토용 초기 가정이며 Checkov 공식 심각도가 아닙니다. 실패 12건의 예외 승인은 아직 이뤄지지 않았고, 실환경 위험도는 추가 평가가 필요합니다.

### 6. OPA Gatekeeper 오탐지 분석 및 예외 정책 튜닝

- **발견한 사례:** 기존 Rego 정책은 `runAsUser`가 없는 Pod를 UID 0으로 간주하여 `runAsNonRoot: true`만 설정된 Pod도 차단했습니다.
- **개선:** 명시적인 Root UID 차단은 유지하면서, UID 미설정 시 `runAsNonRoot: true`를 인정하도록 정책을 수정했습니다.
- **검증 결과(서버 측 Dry Run):** Root 차단 / UID 1000 허용 / `runAsNonRoot: true` 허용 / 설정 없음 차단.
- **예외 실습:** `son-policy-test`에서는 Root 요청을 차단하고, `son-policy-exception`은 해당 **NonRoot Constraint만** 적용 대상에서 제외되는 것을 확인했습니다.
- **주의:** Namespace 전체 예외는 실습용입니다. 다른 보안 정책까지 비활성화하는 것은 아니며, 운영 적용 시에는 승인 절차와 최소 예외 범위가 필요합니다.
- **후속 점검:** Gatekeeper Audit에 나타난 `K8sNativeValidation engine is missing` 상태 원인을 추가 확인해야 합니다.
- **파일:** `policies/gatekeeper/`, `docs/gatekeeper-nonroot-validation.md`.

### 7. Sigstore/cosign 이미지 서명(Signing) 프로세스 도입

- **목적:** 컨테이너 이미지가 지정한 서명 키로 서명되었고, 서명 대상 이미지 Digest와 일치하는지 검증합니다. 서명은 취약점 제거를 대신하지 않습니다.
- **구현:** 로컬 Docker Registry(`127.0.0.1:5000`)에 테스트 이미지를 Push하고, **cosign v3.1.4** 개인키로 Digest에 서명한 다음 공개키로 검증했습니다.
- **자동화:** `scripts/08-local-cosign-sign.sh`가 **Trivy HIGH/CRITICAL 검사 → Registry Push → cosign 서명 → 공개키 검증**을 실행합니다. Trivy 검사에서 위반이 발견되면 서명 단계로 진행하지 않습니다.
- **검증 결과:** 서명된 이미지는 공개키 검증에 성공했고, 별도의 미서명 이미지는 `no signatures found`로 검증에 실패했습니다. 자동화 스크립트도 로컬에서 성공했습니다.
- **키 관리:** 개인키는 저장소 밖의 `~/.config/team4-cosign/cosign.key`에 보관하며 Git에 커밋하지 않습니다.
- **한계:** 로컬 HTTP Registry와 투명성 로그 검증 생략 옵션은 실습 전용입니다. **Kyverno를 통한 Kubernetes 배포 차단과 실제 EKS 적용은 아직 하지 않았습니다.**
- **파일:** `scripts/08-local-cosign-sign.sh`, `docs/cosign-signing-validation.md`.

### 팀원용 로컬 재현 순서

아래 명령어는 **WSL Ubuntu의 `~/projects/team4-startup`**에서 실행합니다. AWS 자원을 생성하는 명령어(`terraform apply`)는 포함하지 않습니다.

**A. Checkov 검사 및 JSON 저장** (12건 위반으로 종료 코드가 1일 수 있음)

```bash
cd ~/projects/team4-startup
source .venv/bin/activate
mkdir -p reports
checkov --config-file .checkov.yaml --var-file infra/terraform.tfvars.example -o json > reports/checkov.json
```

**B. Docker 테스트 이미지 Trivy 검사** (보고서 생성을 위한 `--exit-code 0`; CI 게이트는 실패 코드 사용)

```bash
docker build --build-arg BASE_IMAGE=alpine:3.22 -t team4-test:ci ./containers/test
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 0 --format json --output reports/trivy.json team4-test:ci
```

**C. 위험도 보고서 자동 생성**

```bash
python3 scripts/07-isms-p-risk-report.py
```

자동 보고서는 `reports/isms-p-risk-report.md`에 생성됩니다. GitHub에 보존하는 검증 시점의 사본은 `docs/isms-p-risk-report.md`입니다.

**D. Gatekeeper 적용 상태 확인** (기존 로컬 kind 환경 필요)

```bash
kubectl --context kind-team4 get pods -n gatekeeper-system
kubectl --context kind-team4 get team4nonroot son-require-nonroot -o yaml
```

**E. cosign 서명 자동화** (사전 준비: 로컬 Registry 실행, 테스트 이미지 빌드, cosign 설치, 외부 경로에 개인키·공개키·서명 설정 생성)

```bash
docker ps --filter name=team4-registry
./scripts/08-local-cosign-sign.sh
```

### 검증 자료와 남은 작업

| 자료 | 위치 |
|---|---|
| 초기 ISMS-P/Checkov 매핑 | [`docs/isms-p-checkov-report.md`](docs/isms-p-checkov-report.md) |
| Checkov+Trivy 자동 위험도 보고서 | [`docs/isms-p-risk-report.md`](docs/isms-p-risk-report.md) |
| Checkov 실패 12건 조치·예외 검토 | [`docs/checkov-findings-review.md`](docs/checkov-findings-review.md) |
| Gatekeeper 오탐·예외 검증 | [`docs/gatekeeper-nonroot-validation.md`](docs/gatekeeper-nonroot-validation.md) |
| cosign 서명·검증 결과 | [`docs/cosign-signing-validation.md`](docs/cosign-signing-validation.md) |

**남은 검증:** Checkov 실패 12건에 대한 팀 협의 및 조치·예외 승인, GitHub Actions의 Checkov 정책 위반 해결 여부 확인, Gatekeeper Audit 오류 분석, Kyverno 서명 검증 및 배포 차단 통합, 최종 EKS 검증. **현재 로컬 실습 결과를 실제 AWS 운영환경 검증 결과로 표현하지 않습니다.**
<!-- son-security-status:end -->

---

## Trivy 이미지 취약점 스캔 게이트웨이

### 1. 구현 목적
컨테이너 이미지에 포함된 보안 취약점을 배포 전에 탐지하기 위해 Trivy를 도입하였다.

GitHub Actions와 연동하여 이미지 빌드 후 HIGH 및 CRITICAL 등급의 취약점을 자동 검사하고, 취약점 발견 시 CI 작업이 실패하도록 구성하였다.

### 2. 사용 기술
- Docker: 컨테이너 이미지 빌드
- Trivy: 이미지 취약점 검사
- GitHub Actions: 자동화된 CI 보안 검사
- Alpine Linux: 테스트용 기본 이미지

### 3. 구현 내용
1. GitHub Actions에서 Docker 이미지 자동 빌드
2. Trivy를 활용한 이미지 취약점 검사
3. HIGH 및 CRITICAL 취약점 검출 시 종료 코드 1 반환
4. 검사 결과를 GitHub Actions Artifact로 저장
5. CI 검사 성공 여부를 통해 이미지의 보안 상태 확인

### 4. 주요 구현 파일
- `.github/workflows/trivy.yml`: Trivy 자동 검사 워크플로
- `containers/test/Dockerfile`: 테스트 이미지 생성
- `containers/test/serve.sh`: 컨테이너 실행 스크립트

### 5. 로컬 검사 명령어

```bash
docker build \
  --build-arg BASE_IMAGE=alpine:3.22 \
  -t team4-test:ci \
  ./containers/test

trivy image --scanners vuln \
  --severity HIGH,CRITICAL \
  --exit-code 1 \
  team4-test:ci
```

### 6. ISMS-P 통제항목 연계

| 통제번호 | 인증기준 | 구현 내용 |
|---|---|---|
| 2.8.1 | 보안 요구사항 정의 | HIGH/CRITICAL 취약점 차단 기준 정의 |
| 2.8.2 | 보안 테스트 및 환경 분리 | GitHub Actions 기반 이미지 자동 검사 |
| 2.11.2 | 취약점 점검 및 조치 | 이미지 취약점 탐지 및 검사 결과 저장 |

### 7. 검증 현황
- Trivy 0.76.1 설치 완료
- Alpine 3.22 기반 로컬 이미지 취약점 검사 통과
- GitHub Actions 워크플로 작성 완료
- 로컬 테스트 이미지 빌드 및 Trivy 검사 완료 (HIGH/CRITICAL 0건)
- GitHub Actions 실제 실행 및 취약 이미지 차단 테스트는 추가 확인 필요
- 실제 EKS 배포 차단 연동은 향후 진행 예정
