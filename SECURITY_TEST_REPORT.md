# 보안 시험 결과

작성 기준일 2026-10-23 (Asia/Seoul). `scripts/generate-project-reports.py`가 보관된 증적에서 생성합니다. 작성일이 모든 항목의 재검증일을 뜻하지 않으며, 과거 로컬·모의·plan 성공은 현재 AWS 배포 성공과 구분합니다.

| 기능 | 결과 | 검증 범위 | 증거/제한 |
|---|---|---|---|
| Terraform validate | PASS | static | Provider 스키마 검증. 실제 AWS plan/apply와 구분. |
| Terraform 안전 조건 | PASS | simulated | mock provider: 기본 dry run, 공개 CIDR 금지, OIDC subject, 서명 전용 태그 예외. |
| Checkov | PASS | static | passed=111, failed=0, skipped=23; 예외는 docs/infra-notes.md. |
| 자동복구 단위·통합 테스트 | PASS | simulated | 101개 fake-client/로컬 테스트. 실제 Config/Inspector 이벤트 아님. |
| Docker HTTP | PASS | local | 비 root·읽기전용 rootfs·cap drop 환경에서 TCP8080 응답. |
| Trivy 정상 이미지 | PASS | local | 실제 탐지 패키지 17개, HIGH/CRITICAL 0개. 미탐지 목록은 통과시키지 않음. |
| Trivy 취약 이미지 거부 | PASS | local | 검사 전용 alpine:3.12.0, HIGH/CRITICAL 36건, 실제 프로세스 종료코드1. 실행·배포하지 않음. |
| CycloneDX SBOM | PASS | local | CycloneDX 1.7, 구성요소 100개. 공식 스키마 검사 및 실제 config digest 연결. |
| cosign 로컬 서명 | PASS | local | 실제 OCI 레지스트리 서명·정상키 검증·다른키 거부. 테스트 키/tlog 비활성. AWS OIDC/keyless 검증 아님. |
| NetworkPolicy | PASS | local | 실제 DNS, client→server, 독립 ingress/egress 차단 및 양방향 허용 대조군. |
| ESO Fake/rotation | PASS | local | Kubernetes Secret와 실행중 Pod 볼륨의 값 변화 확인. 원문 출력 없음. AWS SM 검증 아님. |
| Kyverno admission | PASS | local | 정상 Pod 허용 및 잘못된 보안 컨텍스트의 실제 webhook 거부. ECR 서명 정책은 별도 검증 필요. |
| Argo CD GitOps 복구 | PASS | local | Git commit 기준 drift 감지→컨트롤러 복구→통신 재검증. admission과 구분. |
| GitHub Actions CI | PASS | github | 실제 원격 커밋의 실행 결과. 로컬 스크립트 실행을 CI 성공으로 대체하지 않음. 커밋 `bc5fae1a52ad50eddbb4b5cc95833e4a33e9925b` · [실행](https://github.com/realthoroughbred/capstone_1/actions/runs/39948333474). |
| AWS 신원·기존 자원 조회 | PASS | aws | STS 및 EKS·VPC·ECR·Config·OIDC 읽기 전용 조회. 마지막 확인: 2026-10-23T11:48:19.113081+00:00. |
| AWS Terraform plan | PASS | aws | 보관된 최초 AWS provider 계획: {'add': 67, 'change': 0, 'destroy': 0}. 이후 단계별 apply를 시도했으므로 최신 state·증적을 따라야 함. 현재 입력·자원 상태로 새 plan을 확인한 뒤 실행해야 함. docs/AWS_PLAN_REVIEW.md 참고. |
| AWS 초기 IAM·KMS 대조 | PASS | aws | 초기 IAM 정책 6개 및 새 KMS 키의 태그·정책 일치 확인. 모든 배포 API 권한이 충분하다는 의미는 아님. |
| AWS EKS 제어 영역 | PASS | aws | 확인 2026-10-23T11:37:03.569715+00:00: EKS 1.35 제어 영역 ACTIVE, 관리 PC /32 및 기본 SG 차단 확인. 노드·워크로드 성공과 구분. |
| AWS ECR/EKS/Config 실검증 | BLOCKED | aws | EKS 1.35 제어 영역 ACTIVE, CNI/kube-proxy·ECR·OIDC 역할·시험 SG 생성 완료. CNI/OIDC 정책 일치 확인. Terraform 관리 자원 47개. S3 후속 조회 및 노드 RunInstances 권한 누락으로 apply 부분 실패. 노드는 0개, Config·Lambda·ECR 이미지 업로드·EKS 워크로드 검증은 미완료. 관리자 노드/S3 단일 정책 수정 대기. main 전용 GitHub 환경 및 rootless 일회용 runner 등록 완료(오프라인). 신규 자원 정리 미완료, 최대 실습 창 10/24 03:40:30 KST까지. 상태 확인: 2026-10-23T11:57:06.862885+00:00. |
| GitHub AWS 배포 준비 | BLOCKED | github | 확인 2026-10-23T12:00:18.621593+00:00: aws-demo 환경 조회 성공, 사용 가능한 전용 runner 0개. main에 검토한 배포 workflow 반영·환경 보호 설정·AWS 역할 연결 후 실검증 필요. |

## 수정한 실제 실패

- 원본 bare BusyBox 이미지에 Trivy 패키지 인벤토리가 없어 탐지 누락이 발생했습니다. BusyBox httpd는 유지하고 Alpine APK 메타데이터를 추가했습니다. 원본 결과는 `evidence/busybox-baseline/`에 남겼습니다.
- Docker Desktop containerd의 image-store ID가 config digest와 달라, archive의 실제 config 바이트를 해시하도록 수정했습니다. ECR manifest.config.digest도 업로드 후 대조합니다.
- WSL/Desktop loopback 차이를 해결하기 위해 로컬 서명 시험은 같은 격리 네트워크 네임스페이스의 registry를 사용합니다. AWS 배포는 TLS와 OIDC/tlog 검증을 유지합니다.
- CycloneDX 사이트의 HTTP403을 피해 공식 GitHub 스키마를 검증된 commit으로 고정했습니다.
- Kyverno CRD가 지원하는 PodSecurity 버전과 Kubernetes 버전을 구분합니다.

실제 명령과 증적 파일은 `docs/kubernetes-notes.md`, `docs/infra-notes.md`, `evidence/`에서 확인합니다.
