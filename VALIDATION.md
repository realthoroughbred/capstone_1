# 현재 검증 결과 — 2026-11-16

새 브랜치 `codex/finalize-isms-p-20261116`에서 로컬 코드 통합·검증을 진행했다. AWS 생성·변경·삭제/위반 주입/실제 Slack 전송은 **실행하지 않았다**. 기존 인증 만료로 현재 AWS 자원·실제 plan은 NOT_TESTED다.

## 실제 결과

| 범위 | 결과 | 원본 증적 |
|---|---|---|
| 보고서 결함 재현 | 수정 전 8개 하위 사례 실패, 수정 후 회귀 성공 | [수정 전](evidence/finalization-20261116/regressions-before/output.txt), [수정 후](evidence/finalization-20261116/report-regressions-after/output.txt) |
| Python API mock·회귀 | 최종 161개 통과 (WSL Python 3.12, 31.482초) | [전체 시험](evidence/finalization-20261116/unit-161/output.txt), [명령·소스 기록](evidence/finalization-20261116/unit-161/command.json) |
| Terraform | validate 통과, mock plan 10개 통과 | [validate](evidence/finalization-20261116/terraform-validate/output.txt), [mock](evidence/finalization-20261116/terraform-mocks/output.txt) |
| workflow 문법 | actionlint 종료 0 | [기록](evidence/finalization-20261116/actionlint/command.json) |
| Checkov 현재 인프라 | **184통과·3실패·23생략, 종료 1** | [원본 JSON](evidence/finalization-20261116/candidate-checkov/checkov.json), [metadata](evidence/finalization-20261116/candidate-checkov/checkov.json.meta.json) |
| 최초 이미지 gate | HIGH 3·MEDIUM 1, 종료 1로 배포 차단 | [Trivy](evidence/finalization-20261116/candidate-image/trivy.json), [gate](evidence/finalization-20261116/candidate-image/trivy-gate.txt) |
| 패키지 갱신 이미지 | package 17, 발견 0, HTTP·SBOM binding·gate 통과 | [scan](evidence/finalization-20261116/fixed-image/trivy.json), [SBOM](evidence/finalization-20261116/fixed-image/sbom-link.json), [명령](evidence/finalization-20261116/fixed-image-command/command.json) |
| Gatekeeper/Kyverno 제한 | 22개 통과: server dry-run 14, 생성/부재 3, runtime 3, controller 2 | [결과](evidence/finalization-20261116/admission/results.json) |
| 새 Gatekeeper CRD | 생성→Established→template created 대기 성공 | [실제 출력](evidence/finalization-20261116/fresh-crd-command/output.txt) |
| 로컬 공개키 서명 정책 | 6개 통과: dry-run 3, 정상 실제 UID/digest/HTTP 1, 실제 거부/부재 2 | [결과](evidence/finalization-20261116/signature-ready/results.json), [원본 명령](evidence/finalization-20261116/signature-ready/commands.json) |
| NetworkPolicy | DNS·허용·거부 및 ingress/egress 독립 대조군 통과 | [로그](evidence/finalization-20261116/network/network-kind-team4.log) |
| ESO | fake 값 갱신→Secret→실행 Pod volume 반영 통과 | [로그](evidence/finalization-20261116/eso/eso-kind-team4.log) |
| Argo 복원 | 기존 로컬 mirror commit에서 drift→OutOfSync→Git 복원→HTTP 통과 | [결과](evidence/finalization-20261116/gitops-mirror/gitops-kind-team4.json) |
| GitHub 직접 인증 | Deploy Key 생성 HTTP 422 거부. App 대체 코드/권한 검증 추가, 실제 App 미확보 | [실패 로그](evidence/finalization-20261116/gitops-auth-setup/output.txt) |
| SBOM 현재 DB 대조 | COMPLETE, 발견 0, 해당 config digest ledger 기록 | [결과](evidence/finalization-20261116/sbom-rescan/result.json) |
| 로컬 도구 설치 시간 | cache off 63.48초→checksum 검증 cache 26.38초; 전체 CI 시간 아님 | [전](evidence/finalization-20261116/tool-install-no-cache/command.json), [후](evidence/finalization-20261116/tool-install-verified-cache/command.json) |
| 위험 보고서 | 정상 생성 INCOMPLETE/종료 2. 생략 23개를 안전으로 표시하지 않음 | [보고서](evidence/finalization-20261116/baseline-risk-report/isms-p-risk-report.md), [종료 코드](evidence/finalization-20261116/baseline-report-command/command.json) |

## 출처와 재사용 범위

로컬 실행은 기준 commit `4d4a1955d6d2abf168172ed8ee9372ba464632d1` 위의 **미커밋 통합 소스**에서 이루어졌다. 각 metadata에 dirty=true와 실제 source tree SHA256을 남겼다. 이를 원래 4d4a195 코드의 결과로 부르지 않는다. 최초 Checkov와 최초 이미지의 소스 해시는 같고, 최초 위험 보고서는 그 쌍을 읽었다. 패키지 수정 후 이미지는 별도 소스 상태이며 최초 보고서에 새 수치로 끼워 넣지 않았다. 후속 최종 CI는 동일 새 commit/run의 새 결과를 보고서에 연결하도록 구성했다.

수정된 로컬 이미지 config digest는 `sha256:3e55145e080660966aa1c036e1ec5850bd74c99ba5dc1452f793937ab26ab76d`다. 서명 시험의 임시 registry manifest digest는 `sha256:71f44584bf8a80a9601cd15c393abe98cd3f35fb5c3389bee136b7f6d3edceb0`다. ECR digest 또는 승인된 AWS safe image가 아니다.

원격에서 다시 읽은 과거 기록: CI 41291034469 validate/image 성공, risk-report INCOMPLETE exit 2, Checkov **111/0/23**. 과거 로컬 **164/0/23**과 다르다. Son 42482510491 Checkov 실패, 42482510488 Trivy 성공. 과거 AWS 39955813458 deploy 성공은 현재 자원의 존재나 이번 AWS 성공을 뜻하지 않는다.

## 실패 기록도 보존

첫 recorder의 WSL 출력 인코딩 오류, Docker Desktop bind mount로 인한 cwd 소실, 최초 Kyverno readiness 필드 불일치, 병렬 로컬 unit 실행의 cwd 오류 16건, WBS XML 편집 중 두 번의 실패를 삭제하지 않았다. 경로 처리·실제 CRD 상태 필드·XML self-closing/중복 속성을 수정하고 순차 재시험했다. `signature-fixed`, `signature-retry`, `final-unit`, `wbs-update-command`, `wbs-update-retry`, `wbs-tests`에 실패 원본이 있다. SBOM 대조 자체는 성공했으나 동시에 실행된 wrapper의 후행 source 조회는 실패했다. 원본 `result.json`의 시작/종료/명령/소스·digest는 남아 있으며 wrapper 성공이라고 보고하지 않는다.

## 아직 실행하지 못한 검증

현재 AWS 계정/자원/원격 state/실제 Terraform plan, EKS Gatekeeper, ECR OIDC 서명 및 배포, 실제 Secret/KMS 순환, 실제 Config SG 복구, S3/IAM 주기 탐지·복구, 실제 Inspector→외부 CodeBuild→승인 이미지→Pod, CloudWatch 화면, 실제 Slack 전송, GitHub App 직접 GitOps와 workload sync, 전체 CI cold/warm 비교, 전체 복구 1초 목표는 NOT_TESTED다. 인증·외부 연결·승인 이미지·사용자 승인·실제 이벤트가 필요하다.

로컬 원본 evidence는 Git ignore 대상이다. 새 clone에는 자동 포함되지 않는다. 이 PC의 원본 경로/해시와 [실습서](docs/LAB_BOOK.md)를 기준으로 재현하거나 별도 증적 묶음을 전달한다. Secret/state는 묶음에서도 제외한다.
