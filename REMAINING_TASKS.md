# 남은 작업

작성 기준일 2026-10-23 (Asia/Seoul). `scripts/generate-project-reports.py`가 보관된 증적에서 생성합니다. 작성일이 모든 항목의 재검증일을 뜻하지 않으며, 과거 로컬·모의·plan 성공은 현재 AWS 배포 성공과 구분합니다.

- **AWS 신원·기존 자원 조회 — BLOCKED**: 현재 AWS 인증 확인 실패. 최신 조회·권한 확인을 수행하지 못함. 마지막 확인: 2026-10-23T06:05:59.253581+00:00.
- **AWS plan/ECR/EKS/Config/Inspector — BLOCKED**: team4 AWS 로그인 세션 만료. aws login으로 재인증 후 IAM·기존 자원·최신 plan을 재확인해야 함. AWS 작업은 실행하지 않음.
- **GitHub AWS 배포 준비 — BLOCKED**: 확인 2026-10-23T06:07:24.777708+00:00: aws-demo 환경 조회 미확인, 사용 가능한 전용 runner 0개. main에 검토한 배포 workflow 반영·환경 보호 설정·AWS 역할 연결 후 실검증 필요.

AWS 실행 순서: 로그인 갱신 → 관리자 배포 IAM 준비 확인 → 기존 state/자원 확인 → 최신 Terraform plan·비용을 기존 승인 범위와 대조 → apply → ECR 서명·EKS 배포 → SM rotation/서명 정책 → Config 실복구 → 증적 보존 → 이번 신규 자원 정리. Inspector는 별도 범위이며 안전 digest와 연결 가능한 CodeBuild가 준비되어야 합니다.

총예산 상한은 사용자 지정 **180,000원**입니다. 예산은 자원 생성 승인과 별개이며 자동 종료를 보장하지 않습니다. 자세한 절차는 `AWS_DEPLOYMENT_GUIDE.md`, `COST_AND_CLEANUP.md`, `docs/TEAM4_IAM_PERMISSIONS.md`를 참고합니다.

현재 사용자는 신규 생성·최대 8시간 검증·DemoOnly SG 시험·검증 후 신규 자원 정리를 승인했습니다. 같은 범위의 재승인 대신 관리자 IAM 준비 후 실행하며 기존 자원은 변경하지 않습니다.
