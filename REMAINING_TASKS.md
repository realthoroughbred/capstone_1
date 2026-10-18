# 남은 작업

기준일 2026-10-18 (Asia/Seoul). `scripts/generate-project-reports.py`가 실제 증적에서 생성합니다.

- **AWS plan/ECR/EKS/Config/Inspector — BLOCKED**: 신규 생성·최대 8시간 검증·DemoOnly SG 시험·검증 후 신규 자원 정리 승인 완료. 실제 VPC 생성 DryRun 거부와 runtime boundary 부재로 관리자 배포 IAM 준비 대기.

AWS 실행 순서: IAM 사전조회 권한 → 기존 state/자원 확인 → 실제 Terraform plan → 자원·예상 비용·유지시간 승인 → apply → ECR 서명·EKS 배포 → SM rotation/서명 정책 → Config 실복구. Inspector는 별도 승인된 안전 digest와 연결 가능한 CodeBuild가 준비되어야 합니다.

총예산 상한은 사용자 지정 **180,000원**입니다. 예산은 자원 생성 승인과 별개이며 자동 종료를 보장하지 않습니다. 자세한 절차는 `AWS_DEPLOYMENT_GUIDE.md`, `COST_AND_CLEANUP.md`, `docs/TEAM4_IAM_PERMISSIONS.md`를 참고합니다.

현재 사용자는 신규 생성·최대 8시간 검증·DemoOnly SG 시험·검증 후 신규 자원 정리를 승인했습니다. 같은 범위의 재승인 대신 관리자 IAM 준비 후 실행하며 기존 자원은 변경하지 않습니다.
