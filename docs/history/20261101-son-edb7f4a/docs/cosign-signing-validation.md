# Sigstore/cosign 이미지 서명 검증 보고서

## 1. 실습 환경
- 환경: WSL Ubuntu + Docker Desktop
- cosign 버전: v3.1.4
- Trivy 버전: v0.76.1
- Registry: 127.0.0.1:5000
- 대상 이미지: team4-test:ci

## 2. 구현 내용
1. Trivy HIGH/CRITICAL 취약점 검사
2. 로컬 Registry 이미지 등록
3. cosign 개인키를 사용한 이미지 서명
4. 공개키를 이용한 서명 검증
5. 자동화 스크립트 구현

## 3. 검증 결과
| 테스트 | 결과 |
|---|---|
| Trivy HIGH/CRITICAL 검사 | 0건 |
| 이미지 Registry Push | 성공 |
| cosign 이미지 서명 | 성공 |
| 서명된 이미지 검증 | 성공 |
| 서명되지 않은 이미지 검증 | 예상대로 실패 |
| 자동화 스크립트 실행 | 성공 |

## 4. 구현 파일
- scripts/08-local-cosign-sign.sh
- reports/cosign-verify.json
- reports/trivy.json

## 5. 보안 고려사항
- 개인키는 GitHub 저장소 외부에 보관
- 개인키 비밀번호는 별도 안전 관리
- HTTP Registry는 로컬 실습 전용
- 투명성 로그 검증은 실습에서 생략
- 운영환경에서는 HTTPS Registry 및 신뢰할 수 있는 키 관리 필요

## 6. 후속 작업
- Kyverno 이미지 서명 검증 정책 연동
- 실제 EKS 환경에서 배포 차단 검증
- CI/CD 환경의 안전한 서명 키 관리 구성
