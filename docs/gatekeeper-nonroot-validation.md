# OPA Gatekeeper 오탐지 분석 및 예외 정책 검증 보고서

## 1. 실습 환경
- 환경: Docker Desktop + kind (team4)
- Kubernetes 컨텍스트: kind-team4
- 도구: OPA Gatekeeper
- 정책: Team4NonRoot
- 대상: son-policy-test, son-policy-exception

## 2. 오탐지 분석
기존 정책은 runAsUser가 없으면 UID 0으로 판단했다.
이로 인해 runAsNonRoot: true를 지정한 Pod도 차단되었다.

## 3. 정책 개선
- 명시적인 UID 0 차단 유지
- UID 1000 등 NonRoot UID 허용
- UID 미지정 시 runAsNonRoot: true 허용
- 보안 설정이 없는 Pod 차단 유지

## 4. 로컬 검증 결과
| 테스트 | 결과 |
|---|---|
| UID 0 | 차단 성공 |
| UID 1000 | 허용 성공 |
| runAsNonRoot: true | 허용 성공 |
| 보안 설정 없음 | 차단 성공 |
| 일반 Namespace의 Root 요청 | 차단 성공 |
| 예외 Namespace의 Root 요청 | 정책 검사 제외 확인 |

## 5. 예외 정책
- 일반 Namespace: son-policy-test
- 예외 Namespace: son-policy-exception
- excludedNamespaces를 통한 정책 적용 범위 조정
- Namespace 전체 예외는 실습 목적으로만 사용

## 6. 검증 범위 및 후속 조치
- 서버 측 Dry Run으로 Admission 정책 동작 검증
- 실제 Pod 실행 및 EKS 배포 검증은 별도 진행
- Gatekeeper 감사의 K8sNativeValidation 오류 점검 필요
- 운영 환경에서는 최소 범위 예외 및 승인 절차 필요
