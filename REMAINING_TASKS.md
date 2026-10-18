# 남은 작업

기준일 2026-10-18 (Asia/Seoul). `scripts/generate-project-reports.py`가 실제 증적에서 생성합니다.

- **GitHub Actions CI — FAIL**: 실제 원격 커밋의 실행 결과. 로컬 스크립트 실행을 CI 성공으로 대체하지 않음.
- **AWS plan/ECR/EKS/Config/Inspector — BLOCKED**: team4 프로필 인증됨. 자원 조회 IAM 권한 부족 및 유료 생성 승인 전.

AWS 실행 순서: IAM 사전조회 권한 → 기존 state/자원 확인 → 실제 Terraform plan → 자원·예상 비용·유지시간 승인 → apply → ECR 서명·EKS 배포 → SM rotation/서명 정책 → Config 실복구. Inspector는 별도 승인된 안전 digest와 연결 가능한 CodeBuild가 준비되어야 합니다.

총예산 상한은 사용자 지정 **180,000원**입니다. 예산은 자원 생성 승인과 별개이며 자동 종료를 보장하지 않습니다. 자세한 절차는 `AWS_DEPLOYMENT_GUIDE.md`, `COST_AND_CLEANUP.md`, `docs/TEAM4_IAM_PERMISSIONS.md`를 참고합니다.
