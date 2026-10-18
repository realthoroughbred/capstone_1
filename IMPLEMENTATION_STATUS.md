# 구현 및 실검증 현황

기준일 2026-10-18 (Asia/Seoul). `scripts/generate-project-reports.py`가 실제 증적에서 생성합니다.

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
| NetworkPolicy | IMPLEMENTED | NOT_TESTED / local |
| ESO Fake/rotation | VERIFIED | PASS / local |
| Kyverno admission | VERIFIED | PASS / local |
| Argo CD GitOps 복구 | IMPLEMENTED | NOT_TESTED / local |
| GitHub Actions CI | IMPLEMENTED | NOT_TESTED / github |
| AWS plan/ECR/EKS/Config/Inspector | BLOCKED | BLOCKED / aws |

VERIFIED는 표의 범위만 의미합니다. 모의 API 테스트를 AWS 검증으로 계산하지 않습니다.

원본 GitHub main `98850606f7294d4885d97e2891e5535461dbb548`, Checkov feature `9950466a91f773fea1dba8c58b2c5b65b0fe8481`을 비교했습니다. 원래 압축 해제 폴더에 원본 이력을 연결하고 `codex/devsecops-self-healing`에서 작업합니다. Terraform state·인증정보는 업로드하지 않습니다.
