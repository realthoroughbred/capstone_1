# 2026-11-16 AWS 실행 검토안 — 아직 승인·실행하지 않음

현재 단계는 로컬 준비와 모의 검증이다. 이번 실행에서 AWS 생성·수정·삭제, 위반 주입, Slack 전송은 하지 않았다. [과거 승인 문서](history/20261116-pre-finalization/docs/AWS_PLAN_REVIEW.md)는 이번 승인으로 사용할 수 없다.

## 1. 확인된 상태와 먼저 필요한 결정

대상 저장소는 `realthoroughbred/capstone_1`, 준비 브랜치는 `codex/finalize-isms-p-20261116`, 제안 리전은 서울 `ap-northeast-2`다. 기존 `team4` 프로필의 세션이 만료되어 STS 조회가 실패했다. 계정 ID·현재 유료 자원·원격 state는 **NOT_TESTED**다. 로컬 state의 관리 자원 0개와 backup의 63개는 AWS 실재 여부를 뜻하지 않는다.

먼저 사용자가 계정 ID와 Slack 시험 채널을 지정하고 로컬에서 재인증한다. 계정 확인·현황 조회·Terraform plan까지는 읽기 준비 단계다. 실제 plan의 생성/변경/삭제 목록·계정·비용을 확인한 뒤 다음 유료 실행 승인을 받아야 한다. 지금 제안하는 범위는 **전용 실습 자원, 최대 4시간, 예상 USD 3~10 및 검토 예산 USD 20**이다. 예산은 청구 상한을 보장하지 않는다.

현재 Checkov에 시험용 S3의 미해결 실패 3개가 있다. 접근 로그, 교차 리전 복제, 이벤트 알림을 구현·검증하거나 담당자가 범위 변경을 검토해야 한다. 이번 작업에서 생략으로 바꾸지 않았다. 현재 배포 workflow는 검사 실패를 통과시킬 수 없으며, 승인만으로 검사를 우회하지 않는다. 기존 생략 23개도 [예외 검토표](SECURITY_DISPOSITION.md)의 담당자 판단이 필요하다.

## 2. 자원 범위

| 구분 | 계획할 대상 | 기본값·보호 조건 |
|---|---|---|
| 기존 기본 인프라 | VPC·2개 subnet·IGW·route·Flow Log, EKS와 1개 t3.large node, ECR, KMS, 테스트 Secret, OIDC·IRSA·RBAC | 동명 자원 존재부터 조회. 다른 팀 자원 자동 import/교체 금지. state와 실제 소유권 대조 |
| SG | ENI 미연결 DemoOnly SG, Config recorder/rule, EventBridge, Lambda | 기존 recorder 재사용 검토. `enable_self_healing=false`, `healing_dry_run=true` 유지 후 단계 승인 |
| S3/IAM | 비어 있는 `team4-ACCOUNT-ap-northeast-2-healing-sandbox`, 신뢰 정책이 전면 Deny인 `/team4-sandbox/` role, 복구 Lambda, 5분 주기 EventBridge | `enable_resource_healing=false`, dry-run 기본. 다른 버킷/역할·객체/버전이 있는 버킷 거부 |
| 중복·증적 | KMS 암호화 DynamoDB receipts(PITR·TTL), 기존 S3 증적, 실패 SQS | 이벤트별 lease, 실패 재시도, DONE 중복 방지. 이벤트 원본에 Secret 포함 금지 |
| 관측 | EKS Audit Log, CloudWatch dashboard, 복구 로그·실패 queue 지표 | `enable_observability=false`. EKS API/audit/authenticator 등 기존 로그 설정 유지 |
| Slack | 알림 Lambda, 로그 subscription, 기존 Secrets Manager webhook ARN | 기능 생성과 실제 전송 별도. `enable_slack_notifications=false`, `slack_delivery_enabled=false` |
| 이미지 복구 | Inspector/EventBridge/Lambda, ECR enhanced scan, 기존 외부 CodeBuild, 승인 digest SSM parameter | `enable_inspector_response=false`, `inspector_dry_run=true`. 리전 공통 ECR scanning 설정 변경 영향 먼저 검토 |
| EKS 추가 | Gatekeeper CRD/RBAC/webhook, Kyverno, ESO, Argo AppProject/Application | Gatekeeper `son-policy-test`, restricted/ECR 정책 `demo`. 전용 테스트 namespace만 허용 |

실제 Terraform 자원 개수와 재사용/교체 항목은 인증 후 새 plan에서 결정한다. [모의 Terraform 시험](../infra/tests/safety.tftest.hcl)은 실제 AWS plan이 아니다. 외부 CodeBuild·GitHub App·runner·Slack webhook은 자동 생성한 것으로 가정하지 않는다.

## 3. 권한과 연결망

1. 관리자: [기존 경계 정책 안내](TEAM4_IAM_PERMISSIONS.md)와 [추가 권한 조각](../iam/finalization-runtime-fragment.template.json)을 합쳐 검토한다. 정책 버전을 실제로 바꾸지는 않았다. DynamoDB·시험 S3/IAM·알림 Secret의 정확한 ARN으로 제한한다. `AdministratorAccess`를 임시 해결책으로 사용하지 않는다.
2. EKS 운영자: 계정의 access entry와 Kubernetes CRD/RBAC/webhook 설치 권한이 필요하다. Gatekeeper 설치 스크립트는 STS 계정, EKS endpoint, `can-i`를 대조한다.
3. GitHub deploy runner: Python 3.12, Docker, Terraform, GitHub `aws-demo` environment 승인자, OIDC 신뢰, 고정 egress 및 제한된 EKS API 연결이 필요하다. 배포 workflow는 main에서만 수동 실행한다. 이 브랜치 push로 AWS 배포는 실행되지 않는다.
4. CodeBuild: [buildspec](../automation/buildspec-remediate.yml), 검토한 소스 commit, `automation.inspector_worker`의 환경변수, ECR/Inspector/SSM 읽기, EKS의 전용 service account impersonation 권한을 구성한다. EKS private API에 도달 가능한 VPC 연결과 Trivy DB·GitHub·Fulcio/Rekor·ECR에 대한 egress가 필요하다. public subnet만 지정한 CodeBuild ENI에 인터넷이 생긴다고 가정하지 않는다. 기존 NAT/endpoint가 없다면 별도 비용·설계를 승인받는다.
5. Argo GitHub 직접 인증: 저장소 Deploy Key 등록은 실제 HTTP 422로 차단됐다. `contents:read`, 선택 저장소 **capstone_1 하나**, 쓰기 권한 없는 GitHub App 설치가 필요하다. [설정 코드](../scripts/configure-gitops-app-auth.py)는 App을 만들지 않고 사전 설치를 검증한다. 개인키는 Git 밖 파일에서 읽고 출력하지 않는다.
6. Slack: 시험 전용 채널과 webhook Secret ARN을 승인한다. webhook URL 자체는 채팅·tfvars·Git·증적에 넣지 않는다. Lambda outbound HTTPS `hooks.slack.com:443` 필요. 외부 CodeBuild 결과도 알리려면 `remediation_log_group_name`을 정확히 지정한다.

## 4. 읽기 준비 명령

WSL Ubuntu의 저장소 루트에서 실행한다. `ACCOUNT`는 사용자가 확인한 12자리 값이다. 아래 블록은 apply를 포함하지 않는다.

```bash
cd /mnt/d/Downloads/team4-startup-guide/team4-startup
source .venv-ci/bin/activate
export AWS_PROFILE=team4 AWS_REGION=ap-northeast-2 AWS_PAGER=''
aws login --profile team4
read -r -p '확인할 AWS 계정 ID: ' ACCOUNT
[[ "$ACCOUNT" =~ ^[0-9]{12}$ ]] || exit 1
RUN="evidence/aws-preparation-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN"
python scripts/record-command.py --kind AWS_READ_ONLY --output-dir "$RUN/identity" -- \
  aws sts get-caller-identity
python scripts/aws-preflight.py --profile team4 --account "$ACCOUNT" --region "$AWS_REGION"
cp evidence/aws/preflight.json "$RUN/preflight.json"
aws configservice describe-configuration-recorders > "$RUN/config-recorders.json"
aws ecr get-registry-scanning-configuration > "$RUN/ecr-scanning-before.json"
```

인증·계정·권한이 실패하면 후속 AWS 명령을 중단하고 해당 결과를 NOT_TESTED로 남긴다. `aws login`은 사용자의 브라우저 인증이며 비용 자원 생성은 아니다. 기존 로그인 방식이 다른 환경이면 팀 관리자가 정한 방식으로 재인증한다.

Git에서 제외된 `infra/final-demo.tfvars`에 예제의 가짜 계정/주소를 실제 승인 값으로 바꿔 넣는다. 신규 기능은 우선 false, dry-run은 true다. `source_commit`은 검토할 전체 commit으로 지정한다. 기존 state가 올바른 계정·workspace의 것인지 확인하기 전 plan도 진행하지 않는다.

```bash
terraform -chdir=infra init -input=false -lockfile=readonly
terraform -chdir=infra workspace show
terraform -chdir=infra plan -input=false -var-file=final-demo.tfvars -out=../"$RUN"/review.tfplan
terraform -chdir=infra show -no-color ../"$RUN"/review.tfplan > "$RUN/plan.txt"
terraform -chdir=infra show -json ../"$RUN"/review.tfplan > "$RUN/plan.json"
sha256sum "$RUN/review.tfplan" > "$RUN/plan.sha256"
```

plan/state에는 민감한 정보가 있을 수 있어 Git·책에 넣지 않는다. 사용자에게는 자원 주소·동작·개수·비용 영향만 추린 검토표를 보여준다. 변경/삭제가 기존 팀 자원에 닿으면 그 항목을 분리해 승인받는다. `terraform apply`는 해당 저장 plan과 그 해시에 대한 승인 뒤에만 실행한다.

## 5. 4시간 실행 창과 실패 시 중단점

| 시간 | 작업 | 통과 조건·실패 시 조치 |
|---|---|---|
| 0~45분 | 승인 plan 적용, 생성 ID 장부, EKS·정책 준비 | 계정/소유권/endpoint 확인. 실패 시 추가 기능을 켜지 않고 부분 생성 장부 확보 |
| 45~90분 | 동일 commit의 CI→ECR/OIDC→Pod HTTP, Gatekeeper·Kyverno 허용/차단 | scan/SBOM/signature/digest 불일치면 배포 금지. 정상 대조군도 실패하면 정책 성공으로 세지 않음 |
| 90~135분 | NetworkPolicy, Secret 값 변경→ESO→Pod, GitOps 복원 | GitHub 직접 인증과 정확한 synced commit 확인. Secret 원문 출력 금지 |
| 135~180분 | SG 및 전용 S3/IAM, Inspector→승인 이미지→Pod | 먼저 dry-run/권한 부족/중복 검증. 승인 safe digest 없으면 Inspector 교체 NOT_TESTED |
| 180~210분 | 대시보드·승인 Slack 성공/실패 2건, 종합 증적 | 실제 알림 ID/시각, 실패 queue 확인. 1초 목표는 전체 시간을 측정 |
| 210~240분 | 증적 내보내기, 새 자원만 정리, 잔존 조회 | 정리 실패 시 자원 ID·계속 발생 비용·담당자를 기록, 추가 시험 중단 |

실제 finding이 4시간 안에 발생하지 않으면 Inspector 경로는 NOT_TESTED다. 모의 이벤트로 실제 AWS finding 성공을 대신하지 않는다. 지연 때문에 실행 창을 연장하려면 추가 승인받는다.

## 6. 비용 검토

공식 [EKS 가격](https://aws.amazon.com/eks/pricing/)의 표준 지원 cluster $0.10/시간, [공인 IPv4](https://aws.amazon.com/vpc/pricing/) $0.005/시간, [KMS](https://aws.amazon.com/kms/pricing/) 고객 관리 키 $1/월을 참고했다. 리전·지원 기간·현재 할인/무료 크레딧은 실제 계정에서 다시 확인한다. EC2 서울 단가는 이번 인증 실패로 재조회하지 못했으므로 **$0.13/시간 가정**을 사용한다.

4시간 기준 EKS $0.40, 1노드 가정 $0.52, IPv4 $0.02, EBS·로그·Config·Inspector·ECR·S3·DynamoDB·Lambda·CodeBuild·KMS 준비금을 더해 **$3~10 예상**이다. 신규 NAT/endpoint·추가 노드·다른 프로젝트 기존 비용·세금·환율은 포함하지 않았으며 추가 승인이 필요하다. 검토 예산 $20은 알림/중단 판단 기준이지 AWS의 자동 요금 차단 장치가 아니다. 3시간 30분에 시험을 끝내고 정리한다. 장기 증적 보관과 삭제 대기 Secret/KMS 비용도 마지막에 재확인한다.

## 7. Slack 시험안

채널: **사용자 지정 대기**. 전송자: 전용 webhook. 수신 범위: 시험 채널 멤버. 보낼 건수: 정상 복구 1건, 통제된 실패 1건; 같은 이벤트 재수신 시 추가 전송 없음. 실제 문자열은 [알림 코드](../automation/slack_notify.py)의 필드 허용 목록에 따라 만들어진다.

예시 의미: `[team4] status=REMEDIATED resource=<전용 시험 ID> event_id=<실제 ID> source_commit=<전체 commit>`. 실패 예시는 `status=FAILED`다. 이 문장은 **전송 예정 예시이며 실제 전송 로그가 아니다**. Secret 원문, webhook, 정책 전문, 사용자 입력, 멘션은 포함하지 않는다. Lambda 완료 후 응답 유실이 생기면 at-least-once 특성상 중복 전송 가능성이 있으므로 이를 exactly-once라고 표현하지 않는다.

## 8. 정리 계획

먼저 scheduled rule을 끄고, 증적·대시보드 JSON·CloudWatch 로그를 승인된 위치에 내보낸다. S3/IAM 위반 시험은 같은 함수의 allowlist 사전조건으로 정상 재조회 후 끝낸다. SG 시연 스크립트는 자신이 추가한 유일한 규칙만 finally에서 제거한다. 실패 시 ID가 불명확하면 수동 검토한다.

```bash
# 실제 적용/정리를 별도 승인받은 뒤, 같은 RUN·plan·계정에 대해서만 사용
terraform -chdir=infra show -json > "$RUN/current-state.private.json"
python scripts/check-cleanup-plan.py capture \
  --approved-plan "$RUN/plan.json" --current-state "$RUN/current-state.private.json" \
  --pre-apply-inventory "$RUN/names-before-plan.json" \
  --account "$ACCOUNT" --region "$AWS_REGION" --project team4 --output "$RUN/created-ledger.json"
terraform -chdir=infra plan -destroy -var-file=final-demo.tfvars -out=../"$RUN"/destroy.tfplan
terraform -chdir=infra show -json ../"$RUN"/destroy.tfplan > "$RUN/destroy-plan.json"
python scripts/check-cleanup-plan.py check --approved-plan "$RUN/plan.json" \
  --ledger "$RUN/created-ledger.json" --destroy-plan "$RUN/destroy-plan.json" \
  --destroy-plan-file "$RUN/destroy.tfplan" --pre-apply-inventory "$RUN/names-before-plan.json" \
  --output "$RUN/cleanup-scope-check.json"
# 삭제 목록/소유권/증적 export를 확인한 다음 승인된 저장 계획만 적용
terraform -chdir=infra apply ../"$RUN"/destroy.tfplan
```

`names-before-plan.json`은 [기존 정리 장부 규격](../scripts/check-cleanup-plan.py)에 맞춘 **이번 계정의 사전 조회**가 필요하다. 파일이 없다고 과거 파일을 복사해 넣지 않는다. 검사기가 거부하면 삭제하지 않는다. 이 예시는 자동 실행 스크립트가 아니다.

`force_destroy=false`인 ECR·S3가 비어 있지 않으면 destroy가 의도적으로 멈춘다. 새로 만든 저장소의 image/서명/SBOM, S3 모든 version/delete marker를 내보낸 뒤 정확한 ID로 정리하는 별도 검토가 필요하다. 공유 bucket 전체 삭제 금지. Secret은 7일 복구 기간, KMS는 30일 삭제 대기다. 대시보드·Lambda·DDB·로그·SQS·EKS·ENI·EBS·공인 IP·IAM 잔존을 조회하고, 기존 자원은 남았는지 확인한다.

## 9. 승인 요청에 포함할 최종 자료

계정·리전, 실제 plan 해시와 동작 목록, 남은 보안 실패 처리, 최대 4시간/$20 검토 예산, CodeBuild/runner 연결망, Slack 채널과 메시지 2건, 위반 주입 대상 ID, 승인 이미지 digest, 생성 ID 장부·정리 담당자. 아직 이 중 계정 인증·실제 plan·Slack 대상·외부 App/CodeBuild 연결·safe image 승인이 확보되지 않았다. 그 사실을 감추고 실행 승인을 받은 것으로 처리하지 않는다.
