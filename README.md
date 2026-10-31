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
## 로컬 EKS 보안 자동화 구현 및 검증 현황

> 기준일: 2026-11-01
>
> AWS EKS 생성 비용을 고려하여 로컬 Kubernetes(kind) 환경에서
> 보안 기능을 먼저 구현·검증한 후 EKS에 최종 적용할 예정입니다.

### 1. 개발 및 검증 환경

- OS: WSL Ubuntu
- 컨테이너 환경: Docker Desktop
- Kubernetes: kind (team4)
- Checkov: 3.3.29
- Trivy: 0.76.1
- Sigstore/cosign: v3.1.4
- OPA Gatekeeper: 로컬 kind 클러스터에 설치

### 2. ISMS-P 위험도 평가 자동화

Terraform IaC 보안 검사 결과와 컨테이너 이미지 취약점
검사 결과를 활용하여 위험도 보고서를 자동 생성합니다.

**구현 내용**
- Checkov 검사 결과 JSON 분석
- Trivy HIGH/CRITICAL 취약점 결과 연동
- ISMS-P 통제항목 자동 매핑
- 발생 가능성과 영향도 기반 위험점수 계산
- 위험등급 상·중·하 분류
- Markdown 위험도 평가 보고서 자동 생성

**로컬 검증 결과**

| 항목 | 결과 |
|---|---|
| Checkov 전체 검사 | 49건 |
| Checkov 통과 | 37건 |
| Checkov 실패 | 12건 |
| 위험도 상 | 4건 |
| 위험도 중 | 6건 |
| 위험도 하 | 2건 |
| Trivy HIGH/CRITICAL | 0건 |

위험도는 프로젝트 내부 초기 평가 기준으로 산정했으며,
실제 운영환경의 위험도는 추가 검토가 필요합니다.

- 자동화 코드: `scripts/07-isms-p-risk-report.py`
- 결과 보고서: [ISMS-P 위험도 보고서](docs/isms-p-risk-report.md)

### 3. OPA Gatekeeper 오탐지 분석 및 예외 정책

Root 권한 컨테이너 실행을 제한하는 Rego 정책을 개선하고,
정상 요청의 오탐지와 Namespace 예외 적용을 검증했습니다.

**구현 내용**
- Root UID 0 컨테이너 차단
- NonRoot UID 1000 컨테이너 허용
- runAsNonRoot: true 오탐지 개선
- 보안 설정이 없는 Pod 차단
- 특정 Namespace 예외 정책 적용
- Kubernetes 서버 측 Dry Run 검증

**로컬 검증 결과**

| 테스트 | 결과 |
|---|---|
| Root UID 0 | 차단 성공 |
| NonRoot UID 1000 | 허용 성공 |
| runAsNonRoot: true | 허용 성공 |
| 보안 설정 없음 | 차단 성공 |
| 일반 Namespace Root 요청 | 차단 성공 |
| 예외 Namespace Root 요청 | 정책 검사 제외 확인 |

Namespace 전체 예외는 로컬 실습 목적으로만 적용했습니다.
Gatekeeper 감사의 K8sNativeValidation 오류는 추가 점검이 필요합니다.

- 정책: `policies/gatekeeper/`
- 검증 보고서: [Gatekeeper 검증 결과](docs/gatekeeper-nonroot-validation.md)

### 4. Sigstore/cosign 이미지 서명 프로세스

컨테이너 이미지의 서명과 무결성을 검증하기 위해
cosign 기반의 로컬 이미지 서명 절차를 구현했습니다.

**구현 내용**
- 로컬 Docker Registry 구성
- cosign 서명 키 생성
- 이미지 Digest 기반 전자서명
- 공개키를 이용한 서명 검증
- 미서명 이미지 검증 실패 확인
- Trivy 검사 → 이미지 Push → 서명 → 검증 자동화

**로컬 검증 결과**

| 테스트 | 결과 |
|---|---|
| Docker 이미지 Push | 성공 |
| cosign 이미지 서명 | 성공 |
| 서명된 이미지 검증 | 성공 |
| 미서명 이미지 검증 | 예상대로 실패 |
| 로컬 자동화 스크립트 | 실행 성공 |

개인키는 Git 저장소 외부에 보관합니다.
현재 HTTP Registry와 투명성 로그 검증 생략 옵션은
로컬 실습 환경에서만 사용합니다.

- 자동화 코드: `scripts/08-local-cosign-sign.sh`
- 검증 보고서: [cosign 서명 검증 결과](docs/cosign-signing-validation.md)

### 5. 후속 작업

- 보안 검사 및 위험도 평가 자동화 최종 점검
- Gatekeeper 감사 오류 확인
- GitHub Actions 실제 실행 검증
- Kyverno 이미지 서명 검증 정책 연동
- AWS EKS 실제 배포 및 보안 정책 검증

현재 결과는 로컬 환경에서 검증된 내용이며,
AWS EKS 실제 운영환경의 검증 결과는 포함하지 않습니다.
<!-- son-security-status:end -->
