# 현재 통합본 실행 안내

실행 위치는 WSL Ubuntu의 `/mnt/d/Downloads/team4-startup-guide/team4-startup`이다. branch는 `codex/finalize-isms-p-20261116`이다.

1. [실습서 환경 준비](LAB_BOOK.md#3-환경-준비와-증적-규칙)를 실행하고 새 RUN 폴더를 만든다.
2. [코드·Terraform 검증](LAB_BOOK.md#4-로컬-코드와-terraform-검증), [검사·SBOM·보고서](LAB_BOOK.md#5-검사이미지sbom보고서)를 실행한다. 현재 Checkov 실패·생략은 [검토표](SECURITY_DISPOSITION.md)에 남았다.
3. [정책](LAB_BOOK.md#6-gatekeeper와-kyverno의-책임-분리), [통신](LAB_BOOK.md#7-네트워크-통제), [ESO](LAB_BOOK.md#8-secret-값-갱신과-kms-순환), [GitOps](LAB_BOOK.md#9-github-직접-인증과-gitops-복원)의 정상/거부 대조군을 실행한다.
4. 예상 출력은 각 장, 실제 관측 결과와 원본 로그는 [현재 검증](../VALIDATION.md)에 있다. stdout의 PASS만 보지 말고 command.json 종료 코드·Pod UID/digest·원본 JSON을 대조한다.
5. AWS는 [실행 검토안](AWS_EXECUTION_PLAN.md)의 인증·실제 plan·비용·대상 승인 후에만 진행한다. 전체 자동복구와 실패/정리는 실습서 10~15장을 따른다.

이전 통합 안내는 [원본 이력](history/20261116-pre-finalization/docs/INTEGRATION_DEMO.md)에 보존했다. 과거 성공 숫자를 이번 실행 결과로 사용하지 않는다.
