# 보안 시험 결과

기준일 2026-10-18 (Asia/Seoul). `scripts/generate-project-reports.py`가 실제 증적에서 생성합니다.

| 기능 | 결과 | 검증 범위 | 증거/제한 |
|---|---|---|---|
| Terraform validate | PASS | static | Provider 스키마 검증. 실제 AWS plan/apply와 구분. |
| Terraform 안전 조건 | PASS | simulated | mock provider: 기본 dry run, 공개 CIDR 금지, OIDC subject, 서명 전용 태그 예외. |
| Checkov | PASS | static | passed=111, failed=0, skipped=23; 예외는 docs/infra-notes.md. |
| 자동복구 단위·통합 테스트 | PASS | simulated | 70개 fake-client/로컬 테스트. 실제 Config/Inspector 이벤트 아님. |
| Docker HTTP | PASS | local | 비 root·읽기전용 rootfs·cap drop 환경에서 TCP8080 응답. |
| Trivy 정상 이미지 | PASS | local | 실제 탐지 패키지 17개, HIGH/CRITICAL 0개. 미탐지 목록은 통과시키지 않음. |
| Trivy 취약 이미지 거부 | PASS | local | 검사 전용 alpine:3.12.0, HIGH/CRITICAL 36건, 실제 프로세스 종료코드1. 실행·배포하지 않음. |
| CycloneDX SBOM | PASS | local | CycloneDX 1.7, 구성요소 100개. 공식 스키마 검사 및 실제 config digest 연결. |
| cosign 로컬 서명 | PASS | local | 실제 OCI 레지스트리 서명·정상키 검증·다른키 거부. 테스트 키/tlog 비활성. AWS OIDC/keyless 검증 아님. |
| NetworkPolicy | PASS | local | 실제 DNS, client→server, 독립 ingress/egress 차단 및 양방향 허용 대조군. |
| ESO Fake/rotation | PASS | local | Kubernetes Secret와 실행중 Pod 볼륨의 값 변화 확인. 원문 출력 없음. AWS SM 검증 아님. |
| Kyverno admission | PASS | local | 정상 Pod 허용 및 잘못된 보안 컨텍스트의 실제 webhook 거부. ECR 서명 정책은 별도 검증 필요. |
| Argo CD GitOps 복구 | PASS | local | Git commit 기준 drift 감지→컨트롤러 복구→통신 재검증. admission과 구분. |
| GitHub Actions CI | PASS | github | 실제 원격 커밋의 실행 결과. 로컬 스크립트 실행을 CI 성공으로 대체하지 않음. 커밋 `bade7718ba239a8a71f2872068474765c85a3fe9` · [실행](https://github.com/realthoroughbred/capstone_1/actions/runs/39116980831). |
| AWS 신원·기존 자원 조회 | PASS | aws | team4 프로필, 계정 852093844554. STS 및 EKS·VPC·ECR·Config·OIDC 읽기 전용 조회. |
| AWS Terraform plan | PASS | aws | 실제 AWS provider 계획: {'add': 67, 'change': 0, 'destroy': 0}. apply 미실행. docs/AWS_PLAN_REVIEW.md 참고. |
| AWS plan/ECR/EKS/Config/Inspector | BLOCKED | aws | 실제 plan 완료. 정확한 범위의 배포 IAM 준비 및 유료 생성 승인 대기. |

## 수정한 실제 실패

- 원본 bare BusyBox 이미지에 Trivy 패키지 인벤토리가 없어 탐지 누락이 발생했습니다. BusyBox httpd는 유지하고 Alpine APK 메타데이터를 추가했습니다. 원본 결과는 `evidence/busybox-baseline/`에 남겼습니다.
- Docker Desktop containerd의 image-store ID가 config digest와 달라, archive의 실제 config 바이트를 해시하도록 수정했습니다. ECR manifest.config.digest도 업로드 후 대조합니다.
- WSL/Desktop loopback 차이를 해결하기 위해 로컬 서명 시험은 같은 격리 네트워크 네임스페이스의 registry를 사용합니다. AWS 배포는 TLS와 OIDC/tlog 검증을 유지합니다.
- CycloneDX 사이트의 HTTP403을 피해 공식 GitHub 스키마를 검증된 commit으로 고정했습니다.
- Kyverno CRD가 지원하는 PodSecurity 버전과 Kubernetes 버전을 구분합니다.

실제 명령과 증적 파일은 `docs/kubernetes-notes.md`, `docs/infra-notes.md`, `evidence/`에서 확인합니다.
