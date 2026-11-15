# 남은 작업

작성 기준일 2026-10-23 (Asia/Seoul). `scripts/generate-project-reports.py`가 보관된 증적에서 생성합니다. 작성일이 모든 항목의 재검증일을 뜻하지 않으며, 과거 로컬·모의·plan 성공은 현재 AWS 배포 성공과 구분합니다.

- **AWS Inspector→CodeBuild 이미지 교체 — NOT_TESTED**: 코드·모의 검증은 구현됨. 이번 승인 계획에서 Inspector 및 외부 CodeBuild는 비활성이므로 실제 finding·이미지 교체는 미검증.
- **Argo CD GitHub 직접 인증 — NOT_TESTED**: EKS 정책 복구는 고정 commit의 클러스터 내부 읽기 전용 Git 미러로 검증함. private GitHub 직접 인증은 미검증.

재현 순서: 로그인 확인 → 현재 IAM·자원·state 조사 → 새 plan·기간·비용 검토 → 승인된 배포 → 보안·복구 시험 → 증적 보존 → 신규 자원 정리. 위 단계의 이번 실행 결과는 구현 현황을 따릅니다. Inspector는 별도 범위이며 안전 digest와 연결 가능한 CodeBuild가 준비되어야 합니다.

총예산 상한은 사용자 지정 **180,000원**입니다. 예산은 자원 생성 승인과 별개이며 자동 종료를 보장하지 않습니다. 자세한 절차는 `AWS_DEPLOYMENT_GUIDE.md`, `COST_AND_CLEANUP.md`, `docs/TEAM4_IAM_PERMISSIONS.md`를 참고합니다.

이번 승인 범위의 생성·실검증·신규 자원 정리는 완료했습니다. KMS/Secret의 복구 기간을 둔 삭제 예약은 물리적 삭제 완료와 구분합니다. 재배포나 Inspector/CodeBuild 확장에는 새 계획·비용·실행 기간 검토가 필요합니다.
