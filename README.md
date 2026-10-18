Checkov 자동 분석 코드 업로드

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
