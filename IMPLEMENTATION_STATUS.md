# 구현 현황 — 2026-11-16

기준 `origin/codex/integrate-son-security` 4d4a195에서 `codex/finalize-isms-p-20261116`을 만들었다. 시작 시 미커밋 변경은 없었다. 원격 main de11306, Son d2426a5를 다시 조회했다. Son의 최근 변경인 로컬 Kyverno 공개키 정책만 용도를 분리해 반영하고 원본 문서는 이력에 보존했다.

| 구분 | 현재 구현 | 검증 한계 |
|---|---|---|
| 기존 기능 | Terraform, CI, Checkov/Trivy, SBOM/서명, Kyverno, ESO, NetworkPolicy, Argo, SG/Inspector boto3 기능 보존 | 실제 AWS 재검증은 미실행 |
| 보고서 | ImageID/자료형 엄격 검사, 중앙 ISMS 매핑, 출처/생략/종료 상태 분리, 예외 처리표 | 검토 대상은 실제 결과이며 인증 전체 판정 아님 |
| Gatekeeper | controller/Pod 조회 실패 시 fail, CRD 생성/준비 대기, EKS 설치·권한 검사 | 로컬 22개·신규 CRD 성공, EKS 미실행 |
| 이미지 | APK 수정 버전 갱신; worker fresh scan/ECR config/digest/HTTP 검증 | 새 로컬 이미지 성공, AWS safe image 미승인 |
| S3/IAM | 전용 대상·dry-run·최소 권한·전후 조회·DDB 중복/실패 lease | mock 성공; S3 Checkov 3개 실패와 AWS 실제 시험 잔여 |
| 관측/Slack | EKS audit·복구 dashboard, log subscription, 전송 off·필드 허용·중복 처리 | Terraform/mock만 성공, 실제 화면/메시지 없음 |
| 정기 SBOM | 기존 배포 artifact/digest 결합·CVE 대조·새/반복/해결 장부·후속 조사 | 실제 로컬 SBOM 대조 성공; 승인 target/예약 활성화 남음 |
| GitOps | 읽기 전용 GitHub App 설정, 별도 workload template와 네트워크 | 기존 mirror 복원 성공; 직접 인증/새 workload는 NOT_TESTED |
| 문서/WBS | 실습서 본문·AWS 실행안·40행 연결·집계/역할 조회 수정 | 원래 진행률/담당/일정 보존. PPT·리허설·AWS 증거 남음 |

[실제 검증 표](VALIDATION.md), [전체 파일-작업 연결](docs/wbs/task-evidence.json), [후속 우선순위](REMAINING_TASKS.md)를 함께 본다. 코드가 있다는 이유로 WBS를 100%로 올리지 않았다.

최종 코드 commit의 원격 CI: **image 성공, Checkov 131/3/23으로 validate 실패, 위험 보고서 INCOMPLETE exit 2**. [실제 run과 원본 결과](docs/FINAL_CI_RESULT.md)를 참고한다.
