# 남은 작업 — 이번 실행 기준

아래 담당은 제안이며 WBS 원본 배정을 변경하지 않는다. 실제 AWS 시연은 완료되지 않았다.

| 순서 | 남은 작업 | 담당 제안·완료 증거 |
|---|---|---|
| 1 | Checkov 새 S3 접근 로그·CRR·이벤트 알림 3개 처리, 기존 생략 23개 검토 | 손초애+이지민: 통제 설계·새 검사·예외 소유자 판단. gate 우회 금지 |
| 2 | AWS 재인증·계정·현재 자원/state 확인·새 실제 plan | 이지민: 계정/리전/plan hash/자원 목록. 로컬 state 0으로 AWS 부재 추정 금지 |
| 3 | 읽기 전용 GitHub App·Argo 직접 인증·검토 commit workload sync | 원래 작업 담당 김송희와 이지민 협의. 현재 Deploy Key 정책상 차단 |
| 4 | 외부 CodeBuild/runner 연결망·IAM 경계·승인 safe image/SSM | 김송희+이효은: exact commit, digest, 서명/SBOM, 네트워크·권한 |
| 5 | 비용·4시간 실행 창·대상 자원·Slack 채널·정리 승인 | 팀 전체/사용자: [구체 실행안](docs/AWS_EXECUTION_PLAN.md) 검토 |
| 6 | 실제 EKS 정상/차단/네트워크/Secret/GitOps, SG/S3/IAM, Inspector, 관측/알림 | 각 원래 담당: 실제 event·Pod·log·before/after, 실패·정리 증적 |
| 7 | KMS 순환과 Secret 갱신을 별도 검증, 1초 전체 복구 시간 평가 | 이지민/이효은: 외부 발생~검증 완료 시각. 지연 목표 변경은 제안만 |
| 8 | 전체 CI cold/warm 측정, WBS 실제 검증 반영, 발표 PPT·리허설 | 김송희+팀 전체: 같은 commit 시간, 실제 발표 자료·리허설 기록 |

증적 파일을 생성하거나 스크립트를 추가한 것만으로 완료 처리하지 않는다. [WBS 변경 근거](docs/wbs/change-audit.json)는 숫자 진행률을 모두 유지한다. 일정 경과 작업은 재일정 협의가 필요하며 날짜를 자동 연장하지 않았다.
