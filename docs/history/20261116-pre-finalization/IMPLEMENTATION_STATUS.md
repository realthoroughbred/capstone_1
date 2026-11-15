# 구현 및 실검증 현황

작성 기준일 2026-10-23 (Asia/Seoul). `scripts/generate-project-reports.py`가 보관된 증적에서 생성합니다. 작성일이 모든 항목의 재검증일을 뜻하지 않으며, 과거 로컬·모의·plan 성공은 현재 AWS 배포 성공과 구분합니다.

| 기능 | 구현 상태 | 검증 결과/범위 |
|---|---|---|
| Terraform validate | VERIFIED | PASS / static |
| Terraform 안전 조건 | VERIFIED | PASS / simulated |
| Checkov | VERIFIED | PASS / static |
| 자동복구 단위·통합 테스트 | VERIFIED | PASS / simulated |
| Docker HTTP | VERIFIED | PASS / local |
| Trivy 정상 이미지 | VERIFIED | PASS / local |
| Trivy 취약 이미지 거부 | VERIFIED | PASS / local |
| CycloneDX SBOM | VERIFIED | PASS / local |
| cosign 로컬 서명 | VERIFIED | PASS / local |
| NetworkPolicy | VERIFIED | PASS / local |
| ESO Fake/rotation | VERIFIED | PASS / local |
| Kyverno admission | VERIFIED | PASS / local |
| Argo CD GitOps 복구 | VERIFIED | PASS / local |
| GitHub Actions CI | VERIFIED | PASS / github |
| AWS 신원·기존 자원 조회 | VERIFIED | PASS / aws |
| AWS Terraform plan | VERIFIED | PASS / aws |
| AWS 초기 IAM·KMS 대조 | VERIFIED | PASS / aws |
| AWS EKS 제어 영역 | VERIFIED | PASS / aws |
| AWS EKS 노드·애드온 | VERIFIED | PASS / aws |
| AWS ECR 서명·EKS 앱 배포 | VERIFIED | PASS / aws |
| AWS NetworkPolicy | VERIFIED | PASS / aws |
| AWS ESO·비밀값 교체 | VERIFIED | PASS / aws |
| AWS Kyverno 보안 컨텍스트·이미지 제한 | VERIFIED | PASS / aws |
| AWS Kyverno 미서명 이미지 거부 | VERIFIED | PASS / aws |
| AWS Argo CD 정책 복구 | VERIFIED | PASS / aws |
| AWS Config→EventBridge→Lambda SG 복구 | VERIFIED | PASS / aws |
| AWS 신규 유료 자원 정리 | VERIFIED | PASS / aws |
| AWS Inspector→CodeBuild 이미지 교체 | UNVERIFIED | NOT_TESTED / aws |
| Argo CD GitHub 직접 인증 | UNVERIFIED | NOT_TESTED / aws |

VERIFIED는 표의 범위만 의미합니다. 모의 API 테스트를 AWS 검증으로 계산하지 않습니다.

원본 GitHub main `98850606f7294d4885d97e2891e5535461dbb548`, Checkov feature `9950466a91f773fea1dba8c58b2c5b65b0fe8481`을 비교했습니다. 원래 압축 해제 폴더에 원본 이력을 연결하고 `codex/devsecops-self-healing`에서 작업합니다. Terraform state·인증정보는 업로드하지 않습니다.
