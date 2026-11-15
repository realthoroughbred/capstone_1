# 최종 통합 작업 기록

기준일: 2026-11-16. 브랜치: `codex/finalize-isms-p-20261116`.
AWS 변경·위반 주입·Slack 전송 승인 전 준비 작업이다.

1. 원격 재조회: main `de11306`, 기존 통합 `4d4a195`, 손초애 `d2426a5`.
   작업 트리는 시작 시 깨끗했다. main 이후 기능을 버리지 않고 통합본을 기준으로 작업한다.
   손초애의 11월 변경은 로컬 Kyverno 정책과 설명이다. 원본은 이력으로 보존했다.
2. CI 41291034469 원본 로그 재조회: Checkov **111/0/23**(통과/실패/생략),
   validate/image 성공, risk-report 정상 생성 후 INCOMPLETE exit 2.
   11월 1일 로컬 164/0/23과 다르다. 현재 실행 수치로 재사용하지 않는다.
   기존 artifact API는 빈 목록을 반환했다. 로그는 `evidence/finalization-20261116/historical-ci-*.log`.
3. AWS 프로필 team4는 만료. 현재 자원의 존재·부재는 NOT_TESTED.
   `aws-team4-region/command.json`에 읽기 전용 조회 실패를 보존했다.
4. WBS 40개 세부행 확인: 집계 범위 17:51, 역할 조회 A6:B7, 팀 평균 E6:E7 오류.
   원본 복사본과 SHA256은 [wbs](wbs/). 진행률·담당자 숫자는 근거 없이 변경하지 않는다.
5. 보고서 결함 재현: 이미지 ID 누락, 잘못된 배열 자료형, 없는 통제 매핑으로
   회귀시험 8개 하위 사례 실패. 수정 후 보고서 22개, 스캔 게이트 6개 성공.
   로그: `regressions-before`, `report-regressions-after`, `coverage-regressions`.

원본 증적 루트: `evidence/finalization-20261116/`. 각 시험은 새 하위 폴더를 사용한다.
후속 구현·시험은 아래에 실제 결과가 확보되는 대로 추가한다.

6. S3/IAM 전용 복구·DynamoDB 중복 처리, CloudWatch dashboard·Slack 기본 전송 off,
   기존 SBOM의 정기 CVE 대조, GitHub App 대체 인증, 별도 GitOps workload,
   Inspector manifest/config 및 교체 후 HTTP 검증을 구현했다. AWS는 미실행이다.
7. 실제 로컬 Gatekeeper/Kyverno 제한 22개, 신규 CRD 생성 대기, 로컬 이미지 서명 6개가 통과했다.
   정상 Pod UID/digest/HTTP와 거부 Pod 부재를 구분했다. ESO·통신·기존 mirror GitOps도 통과했다.
8. Checkov 184/3/23. 새 시험 S3 접근 로그·복제·이벤트 3개는 미해결이다.
   최초 이미지 HIGH 3/MEDIUM 1은 gate가 차단했다. APK 갱신한 새 이미지는 발견 0/package 17,
   SBOM·HTTP 통과. 과거/최초 결과에 새 수치를 덮어쓰지 않았다.
9. 최종 Python 161개 통과, Terraform mock 10개, validate·actionlint 통과.
   WSL Docker bind mount 병렬 실행 오류와 WBS XML 실패를 보존하고 수정 후 재시험했다.
10. WBS 40개 연결·원본 진행률/담당/일정 보존, 집계·역할 수식 수정본을 생성했다.
    [실습서 본문](LAB_BOOK.md), [새 AWS 실행안](AWS_EXECUTION_PLAN.md), [검증 결과](../VALIDATION.md)를 작성했다.
    과거 AWS 승인·비용·보고서도 원본 바이트로 이력 보관 후 현재 안내를 갱신했다.
