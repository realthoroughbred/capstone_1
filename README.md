# capstone_1 — AWS EKS 보안 통제·자동복구 실습

선정한 ISMS-P 기술 통제, Terraform·이미지 검사, SBOM·서명, 배포 차단, ESO·NetworkPolicy, 위반 감지·제한된 복구, 증적·위험 보고서를 연결하는 프로젝트다. 별도 서비스 개발이 아니라 실제 AWS 시연과 기술 실습서가 결과물이다.

2026-11-16 현재 **로컬 통합·검증 및 AWS 실행 준비 단계**다. AWS 변경/위반 주입/Slack 전송은 하지 않았다. Checkov 184통과·3실패·23생략으로 아직 전체 검사가 통과한 상태가 아니다. 최초 이미지 HIGH 3건을 패키지 갱신으로 수정했고 새 로컬 이미지는 HIGH/CRITICAL 0건이다. 실제 AWS 및 GitHub 직접 인증은 남았다.

- [따라 하는 실습서 본문](docs/LAB_BOOK.md)
- [현재 시험 결과와 원본 증적](VALIDATION.md)
- [WBS 수정본](docs/wbs/finalization-11week-reviewed.xlsx), [원본](docs/wbs/original-11week.xlsx), [40개 작업 근거](docs/wbs/task-evidence.json)
- [구현 현황](IMPLEMENTATION_STATUS.md), [남은 작업과 담당 제안](REMAINING_TASKS.md)
- [미해결 검사·예외 검토](docs/SECURITY_DISPOSITION.md)
- [새 AWS 실행·비용·정리 검토안](docs/AWS_EXECUTION_PLAN.md)
- [과거 보고서 원본 이력](docs/history/README.md)

WSL Ubuntu의 이 저장소에서 `source .venv-ci/bin/activate` 후 `python -m unittest discover -s tests -v`로 API mock/회귀 시험을 시작할 수 있다. 실제 로컬 Kubernetes 시험 및 AWS 승인 이후 명령은 실습서 순서를 따른다. 원래 통합본·팀원 branch의 Terraform/CI를 통째로 덮어쓰지 않았고 main에는 합치지 않았다.

최종 코드 commit의 원격 CI: **image 성공, Checkov 131/3/23으로 validate 실패, 위험 보고서 INCOMPLETE exit 2**. [실제 run과 원본 결과](docs/FINAL_CI_RESULT.md)를 참고한다.
