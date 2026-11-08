# Kyverno 이미지 서명 검증 결과 보고서

## 1. 목적
cosign으로 서명한 컨테이너 이미지만 Kubernetes 배포 요청에서
허용하고, 미서명 이미지는 차단하도록 정책을 구현한다.

## 2. 실습 환경
- Kubernetes: kind-team4 (v1.35.0)
- Kyverno: v1.19.1
- Helm Chart: 3.9.1
- cosign: v3.1.4
- Registry: team4-registry:5000
- 테스트 Namespace: son-kyverno-sign-test

## 3. 구현 내용
- Kyverno ImageValidatingPolicy 기반 서명 검증
- NamespacedImageValidatingPolicy 적용
- cosign 공개키 기반 이미지 서명 확인
- 미서명 이미지 배포 요청 거부
- 로컬 HTTP Registry 연동

## 4. 검증 결과

| 검증 항목 | 결과 |
|---|---|
| Kyverno 컨트롤러 실행 | 성공 |
| 서명 검증 정책 READY | true |
| Registry 연결 | 성공 |
| 서명된 이미지 생성 요청 | 허용 |
| 미서명 이미지 생성 요청 | 차단 |

### 서명된 이미지
pod/signed-test created (server dry run)

### 미서명 이미지
Policy require-team4-cosign failed:
Image must have a valid Team4 cosign signature

## 5. 문제 해결 기록
cosign 3에서 생성한 서명을 Kyverno가 찾지 못하는 문제가 발생했다.

기존 서명 방식의 .sig 태그를 추가한 후
Kyverno의 정상 서명 이미지 검증에 성공했다.

## 6. 검증 범위 및 한계
- Kubernetes 서버 측 Dry Run으로 검증했다.
- 실제 Pod 실행 검증은 아직 수행하지 않았다.
- 정책은 테스트 Namespace에만 적용했다.
- 정책의 이미지 참조 패턴에 일치하는 이미지만 검사한다.
- HTTP Registry 및 투명성 로그 검증 생략은 로컬 실습 전용이다.
- 실제 AWS EKS 적용 및 검증은 수행하지 않았다.

## 7. 관련 파일
- policies/kyverno/verify-local-cosign.yaml
- scripts/08-local-cosign-sign.sh
- docs/cosign-signing-validation.md
