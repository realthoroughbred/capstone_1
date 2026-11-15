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
- 서명된 이미지의 실제 Pod 실행까지 검증했다.
- 정책은 테스트 Namespace에만 적용했다.
- 정책의 이미지 참조 패턴에 일치하는 이미지만 검사한다.
- HTTP Registry 및 투명성 로그 검증 생략은 로컬 실습 전용이다.
- 실제 AWS EKS 적용 및 검증은 수행하지 않았다.

## 7. 관련 파일
- policies/kyverno/verify-local-cosign.yaml
- scripts/08-local-cosign-sign.sh
- docs/cosign-signing-validation.md


## 8. 실제 Pod 실행 검증

### 검증 환경
- 검증일: 2026-11-08
- Kubernetes: kind-team4
- Namespace: son-kyverno-sign-test
- Pod: signed-runtime-test-v2
- 이미지: team4-registry:5000/team4-test:ci

### 검증 결과

| 항목 | 결과 |
|---|---|
| Kyverno 서명 검증 | 성공 |
| 서명된 이미지 생성 | 허용 |
| 미서명 이미지 생성 | 차단 |
| 이미지 다운로드 | 성공 |
| 실제 Pod 실행 | 1/1 Running |

### 발생한 문제 및 해결

초기 실행에서 ImagePullBackOff 오류가 발생했다.

원인은 로컬 Registry가 HTTP 방식인데
kind 노드의 containerd가 HTTPS로 접속했기 때문이다.

kind의 control-plane과 worker 노드에
HTTP Registry 접속용 hosts.toml 설정을 추가했다.

이후 이미지 다운로드에 성공했으며,
서명된 이미지를 사용한 Pod가 정상 실행됐다.

### 검증 범위

로컬 Kubernetes 환경에서 서명 검증,
미서명 이미지 차단 및 실제 Pod 실행까지 확인했다.

AWS EKS 환경 적용 및 검증은 아직 수행하지 않았다.
로컬 HTTP Registry 설정은 운영환경에 그대로 적용하지 않는다.
