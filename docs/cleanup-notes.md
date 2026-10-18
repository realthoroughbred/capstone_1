# 승인된 신규 AWS 자원 정리 절차

사용자는 [AWS_PLAN_REVIEW.md](AWS_PLAN_REVIEW.md)의 신규 생성, 최대 8시간 실검증, ENI 미연결 DemoOnly SG의 TCP22 일시 공개·자동 복구, **검증 후 이번에 만든 자원의 정리까지 승인**했다. 같은 범위의 정리에 다시 승인을 요구하지 않는다. 기존 자원·공유 자원·다른 프로젝트로 범위를 넓히는 작업은 포함하지 않는다. 이 문서는 운영 절차이며, 작성 시점에는 AWS 생성·삭제를 실행하지 않았고 실제 생성 ID도 없다.

첫 유료 자원 생성 시각과 8시간 종료 시각을 UTC와 KST(UTC+9)로 함께 기록한다. 설치·문제 조사도 이 시간에 포함하고, 삭제 대기 시간을 확보하도록 검증을 일찍 마친다. 실패하거나 필수 권한이 없으면 남은 실험을 중단하고 **이미 만든 승인 범위 자원부터 정리**한다. 8시간이 지나면 자동으로 비용이 멈추는 장치는 없다.

## 1. 원본 계획과 신규 ID 고정

작업은 저장소 루트의 WSL Bash에서 수행한다. 계정 `852093844554`, 리전 `ap-northeast-2`, profile `team4`를 재확인한다. 아래 명령은 실제 운영 때 사용할 절차이며 아직 실행한 결과가 아니다. 증적 폴더는 Git에서 제외하고 접근 권한을 제한한다. Terraform JSON에는 평문 민감 값이 포함될 수 있으므로 채팅·PR·공개 로그에 붙이지 않는다.

```bash
export AWS_PROFILE=team4 AWS_REGION=ap-northeast-2 AWS_PAGER=""
umask 077
mkdir -p evidence/cleanup
aws sts get-caller-identity --profile team4 --region ap-northeast-2
# 최초 검토한 create-only plan JSON을 보존한다. 이후 bootstrap 재계획으로 덮어쓰지 않는다.
# 이 프로젝트의 원본: evidence/aws/demo-plan.json (67 create, 기존 managed state 없음)
terraform -chdir=infra show -json > evidence/cleanup/state-after-apply-01.json
python scripts/check-cleanup-plan.py capture \
  --approved-plan evidence/aws/demo-plan.json \
  --pre-apply-inventory evidence/aws/names-before-plan.json \
  --current-state evidence/cleanup/state-after-apply-01.json \
  --account 852093844554 --region ap-northeast-2 --project team4 \
  --output evidence/cleanup/ledger-01.json
```

`capture`는 원본 plan의 `prior_state`에 기존 managed 자원이 없는지 확인하고, 실제 state의 주소·type·ID·ARN을 기록한다. 현재 원본에는 data source만 있다. Terraform 1.12.2/JSON format 1.2는 빈 state일 때 `prior_state` 자체를 생략할 수 있다. 이 경우에는 확인된 버전 형식과 별도 생성 전 읽기 조사 JSON이 함께 있어야 통과하며, 조사 자료의 hash도 ledger에 고정한다. 다른 버전이나 미해결 조회 오류는 거부한다. [Terraform 1.12.2 JSON 생성 코드](https://github.com/hashicorp/terraform/blob/v1.12.2/internal/command/jsonplan/plan.go).

부분 apply라면 실제 생성된 부분만 기록한다. 신규 VPC에 속해야 하는 자원의 `vpc_id`도 대조한다. 데이터 소스, secret 값, 전체 policy 본문은 ledger에 복사하지 않는다. 새 상태를 추가할 때는 번호를 올리고 이전 ledger를 남긴다.

**이 검사는 로컬 파일 간 일치만 확인한다.** state·태그만으로 소유권을 증명하지 않는다. 생성 전 `names-before-plan.json`/`preflight.json`, 실제 생성 응답·시각, 승인된 원본 계획, AWS 재조회 결과를 함께 대조한다. 관리자가 이번 계획을 위해 만든 KMS를 import했다면 원래 create 주소, 생성 전 부재, 정확한 새 key ID와 생성 기록을 확인한다. 기존 key·OIDC·Config recorder를 편의상 import해서 삭제 대상으로 바꾸지 않는다. `runtime boundary`와 사용자에게 연결한 관리자 정책은 Terraform 밖의 권한 체계이므로 이 절차로 삭제하지 않는다.

EC2 인스턴스·ASG·EBS·ENI처럼 node group이 만든 하위 자원은 Terraform 개별 주소가 없을 수 있다. 실제 node group의 ASG, 인스턴스, subnet/VPC, 볼륨 attachment와 `DeleteOnTermination` 관계를 별도 JSON으로 기록한다. 소유권이 불분명한 ENI나 기존 VPC 종속성이 보이면 강제 detach/delete를 하지 않는다.

## 2. 실험 종료와 새 쓰기 중지

1. SG 실험 결과·Config 실제 평가·Lambda 로그·시간 측정·오류 큐 상태를 보존한다. 테스트가 실패했다면 `13-sg-healing-demo.py`가 만든 **정확한 rule ID 한 개**의 제거 여부를 확인한다. 수동 제거는 자동 복구 성공으로 보고하지 않는다. DemoOnly/Project 태그·계정·ENI 미연결 조건이 바뀌었으면 자동 조치를 중단한다.
2. 배포 workflow와 실험 실행을 끝내고, 이번에 만든 EventBridge rule만 비활성화한다. Lambda의 실행·재시도와 새 evidence 쓰기가 멎었는지 확인한다. 실패 큐는 비우지 않고 필요한 메시지와 원인을 먼저 보존한다. 메시지를 읽으면 visibility timeout이 바뀔 수 있으므로 작업 기록을 남긴다.
3. 이번에 만든 Config recorder만 중지하고 `recording=false`를 조회한다. Config 전달 채널 삭제 전에 recorder를 중지해야 한다. 기존·조직 관리 recorder에는 적용하지 않는다. [AWS Config 삭제 조건](https://docs.aws.amazon.com/config/latest/APIReference/API_DeleteDeliveryChannel.html).

```bash
# EVENT_RULE / CONFIG_RECORDER는 ledger와 실제 조회에서 확인한 이번 신규 자원의 이름이다.
aws events disable-rule --name "$EVENT_RULE" --region ap-northeast-2
aws configservice stop-configuration-recorder \
  --configuration-recorder-name "$CONFIG_RECORDER" --region ap-northeast-2
aws configservice describe-configuration-recorder-status \
  --configuration-recorder-names "$CONFIG_RECORDER" --region ap-northeast-2
```

기존 Config 기록에는 이번 SG 삭제 평가가 남지 않을 수 있으므로 마지막 평가와 이후 실제 삭제 확인을 구분한다. 중지 직후에도 지연된 전달·재시도가 있을 수 있다. 백업 후 목록을 다시 읽고 새 항목이 있으면 해당 항목도 내보낸다. 버킷 정책을 느슨하게 하거나 보존 보호를 해제해 정리를 강행하지 않는다.

## 3. S3 모든 버전과 ECR 이미지 내보내기

`BUCKET`, `REPOSITORY`, `REPOSITORY_URI`는 ledger의 정확한 새 bucket/repository와 일치해야 한다. 단순 `team4` 접두사 검색 결과 전체를 정리 대상으로 삼지 않는다. 콘솔 이름뿐 아니라 계정·리전·ARN·생성 기록을 확인한다.

```bash
aws s3api list-object-versions --bucket "$BUCKET" \
  --expected-bucket-owner 852093844554 --output json \
  > evidence/cleanup/s3-versions-before.json
aws s3api list-multipart-uploads --bucket "$BUCKET" \
  --expected-bucket-owner 852093844554 --output json \
  > evidence/cleanup/s3-multipart-before.json
aws ecr describe-images --registry-id 852093844554 \
  --repository-name "$REPOSITORY" --output json \
  > evidence/cleanup/ecr-images-before.json
```

AWS CLI 자동 pagination을 유지한다. `--no-paginate`, 일부 `--max-items`만 저장하거나 첫 페이지만 읽는 방식은 쓰지 않는다.

| 자료 | 내보내기와 확인 |
| --- | --- |
| S3 `Versions` | 각 `(Key, VersionId)`를 `get-object --version-id`로 다운로드한다. 파일명은 키를 경로로 직접 쓰지 말고 일련번호 또는 키/버전의 SHA256으로 만든다. 원래 Key·VersionId·Size·파일명·SHA256을 manifest에 기록한다. 크기와 제공된 checksum을 대조하고, checksum이 없으면 같은 버전을 재다운로드해 SHA256을 대조한다. |
| S3 `DeleteMarkers` | 본문은 없으므로 Key·VersionId·LastModified를 manifest에 보존한다. 단순 재귀 다운로드나 `aws s3 rm --recursive`로는 과거 버전과 마커가 모두 처리되지 않는다. [버전 삭제 동작](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html) |
| ECR | 모든 tagged/untagged digest, 이미지 manifest/index, 하위 플랫폼, cosign `.sig`/`.att` 및 OCI referrer를 보존한다. 이미지 목록만 저장하는 것은 이미지 백업이 아니다. 각 digest를 OCI layout으로 받아 전체 blob과 descriptor를 검사하고, digest/tag 매핑·서명 검증·SBOM 결과를 별도 보존한다. 지원되지 않는 artifact가 있으면 누락한 채 성공 처리하지 않는다. |
| 기타 | Terraform 원본/최종 plan·state·ledger, Config 평가·설정, 로그, SG 실험 증거, 실패 큐 조사 결과를 접근 통제된 로컬 저장소에 내보낸다. secret **값**과 AWS/GitHub 인증 token은 일반 증적에 넣지 않는다. 임시 demo secret은 복원용 값 백업이 필요하지 않다. |

각 S3 객체에 대한 명령 형태는 다음과 같다. `KEY`, `VERSION_ID`, `LOCAL_FILE`은 검토한 manifest의 한 행을 그대로 사용한다.

```bash
aws s3api get-object --bucket "$BUCKET" --expected-bucket-owner 852093844554 \
  --key "$KEY" --version-id "$VERSION_ID" --checksum-mode ENABLED "$LOCAL_FILE" \
  > "$LOCAL_FILE.metadata.json"
sha256sum "$LOCAL_FILE"
```

ECR 인증은 기존 배포용 로그인 절차를 사용하며 비밀번호를 출력하지 않는다. digest마다 다음처럼 OCI 디렉터리를 만든다. `--platform`을 지정하지 않아 index의 모든 플랫폼을 보존한다. 소스 digest가 로컬 `index.json`에서 참조되는지, 모든 descriptor의 blob이 존재하고 크기·SHA256이 일치하는지 재귀적으로 확인한다. `crane pull` 종료 코드나 디렉터리 존재만으로 완료 판정하지 않는다. [crane pull 공식 문서와 OCI 처리](https://github.com/google/go-containerregistry/blob/v0.20.3/cmd/crane/cmd/pull.go).

```bash
crane pull "$REPOSITORY_URI@$DIGEST" "$OCI_DIRECTORY" --format=oci --annotate-ref
```

모든 백업을 암호화·접근 통제된 위치에 보존하고 manifest를 해시로 고정한다. 프로젝트 KMS가 삭제 대기 상태가 되면 복호화할 수 없으므로 **해독 가능한 로컬 백업 검증은 KMS 삭제 예약보다 먼저** 끝낸다. [KMS 삭제 대기 동작](https://docs.aws.amazon.com/kms/latest/developerguide/key-state.html).

## 4. 검증된 신규 bucket/repository의 내용만 정리

백업 manifest의 모든 항목이 검증되면, 승인된 신규 bucket의 정확한 Key+VersionId와 신규 repository의 정확한 digest만 개별 삭제한다. 두 컨테이너의 `force_destroy=false`/`force_delete=false`를 유지한다. 이는 이미 승인된 신규 자원 정리에 포함되며 새 삭제 승인을 반복해서 요구하지 않는다.

```bash
# 백업 검증된 manifest 한 행에 대해서만 실행한다. 목록 전체를 즉시 삭제하는 파이프는 쓰지 않는다.
aws s3api delete-object --bucket "$BUCKET" --expected-bucket-owner 852093844554 \
  --key "$KEY" --version-id "$VERSION_ID"
aws ecr batch-delete-image --registry-id 852093844554 \
  --repository-name "$REPOSITORY" --image-ids "imageDigest=$DIGEST"
```

S3 delete marker도 정확한 VersionId를 지정한다. multipart upload가 있으면 upload ID·키·소유권을 기록하고 이번 작업의 중단된 업로드만 abort한다. Object Lock/MFA Delete 등 예상하지 못한 보호가 보이면 해제하지 않고 원인을 확인한다. ECR는 index/manifest list가 참조하는 이미지의 삭제를 거부할 수 있으므로 백업된 상위 index부터 처리한다. 응답의 `failures`가 비었는지 확인하고, 실패 항목을 성공으로 집계하지 않는다. [ECR digest 삭제와 참조 관계](https://docs.aws.amazon.com/AmazonECR/latest/userguide/delete_image.html).

목록을 다시 읽어 S3 `Versions`, `DeleteMarkers`, multipart uploads와 ECR 모든 digest가 비었는지 확인한다. 새 객체가 생겼다면 중지·백업·검증을 반복한다. 원인을 모르는 항목은 삭제하지 않는다. 백업 실패 시 EKS/노드 등 다른 확인된 신규 자원은 구체적인 별도 삭제 계획을 만들어 우선 정리할 수 있지만, S3/ECR와 그 데이터를 해독하는 KMS는 보존한다. 보존 대상의 `state rm`으로 책임을 숨기지 않는다.

## 5. 최종 destroy plan 검사와 실행

EKS가 살아 있는 동안 `kubectl --context team4-eks get svc,ingress,pvc -A`와 `get pv`로 이번 배포가 만든 종속성을 확인한다. 현재 기본 구성에는 ALB/PVC가 없지만 새로 발견한 항목을 추정으로 삭제하지 않는다. 이번에 만든 Service/Ingress/PVC라면 controller가 살아 있을 때 정상 Kubernetes 삭제를 하고 AWS 하위 자원 종료를 기다린다. Argo CD가 재생성하지 않도록 이번 Application의 동기화를 먼저 중지한다. 외부 finalizer를 강제 제거하지 않는다. [EKS 삭제 선행 조건](https://docs.aws.amazon.com/eks/latest/userguide/delete-cluster.html).

```bash
terraform -chdir=infra plan -destroy -var-file=demo.tfvars \
  -out=../evidence/cleanup/destroy-01.tfplan
terraform -chdir=infra show -json ../evidence/cleanup/destroy-01.tfplan \
  > evidence/cleanup/destroy-01.json
terraform -chdir=infra show -no-color ../evidence/cleanup/destroy-01.tfplan \
  > evidence/cleanup/destroy-01.txt
python scripts/check-cleanup-plan.py check \
  --approved-plan evidence/aws/demo-plan.json \
  --pre-apply-inventory evidence/aws/names-before-plan.json \
  --ledger evidence/cleanup/ledger-01.json \
  --destroy-plan evidence/cleanup/destroy-01.json \
  --destroy-plan-file evidence/cleanup/destroy-01.tfplan \
  --output evidence/cleanup/destroy-check-01.json
# 로컬 검사 PASS, 실제 신규 소유권, 백업 검증, 계정/리전 및 사람이 읽는 plan을 모두 대조한다.
# report의 destroy_plan_file_sha256과 같은 파일인지 실행 직전 다시 확인한다.
sha256sum evidence/cleanup/destroy-01.tfplan
terraform -chdir=infra apply ../evidence/cleanup/destroy-01.tfplan
```

`demo.tfvars`는 **실제 apply에 사용한 동일한 비공개 tfvars 경로로 바꾼다**. `-refresh=false`나 임의 `-target`, `-lock=false`로 보호를 피하지 않는다. helper는 변경·교체·import·계정/리전/ID 차이·추가 managed 자원·불완전 plan을 거부한다. `check`는 로컬 `terraform -chdir=infra show -json`으로 binary를 직접 읽어 제공 JSON과 대조하며, 읽기 전후와 검사 종료 때 binary SHA256도 대조한다. Terraform 명령을 사용할 수 있는 WSL에서 실행한다. 이 명령은 저장된 계획을 읽으며 apply나 AWS API 호출을 실행하지 않는다. [Terraform show](https://developer.hashicorp.com/terraform/cli/commands/show).

`LOCAL_SCOPE_CHECK_PASSED`는 클라우드 소유권·백업·삭제 성공을 의미하지 않는다. 원본 생성 plan과 조사 자료는 신뢰된 비공개 증적으로 유지하고, 검사 뒤 파일 변경이 있으면 재검사한다. 실제 apply에는 report에 기록된 hash와 같은 binary를 사용한다.

Terraform의 실제 의존 그래프로 node group→cluster→네트워크, Config status 중지→delivery channel/recorder, 데이터 사용 자원→KMS 순서를 처리한다. 일부 삭제 실패 시 성공한 자원까지 재생성하지 않는다. state를 저장하고 새 destroy plan을 만들어 같은 ledger와 대조한다. 이전 ledger에만 남은 주소는 실제 AWS 부재가 확인되기 전까지 `UNKNOWN`이다.

부분 apply가 API 응답 유실 등으로 state에 기록하지 못한 자원을 남기면 먼저 계정·새 ID·생성 기록을 조사한다. 이번 승인 범위의 신규 자원임이 확인될 때만 정확한 주소로 state 복구/import 후 ledger를 새로 만든다. 기존 자원을 import해 삭제하거나 state 파일·lock을 임의로 지우지 않는다. 권한 오류는 정확한 자원/action을 관리자에게 전달하고, 거부된 보호를 광범위한 정책이나 force 옵션으로 우회하지 않는다.

## 6. 종료 판정

| 확인 | 종료 증거 |
| --- | --- |
| 유료 실행 자원 | ledger와 하위 자원 목록의 EKS/node group/EC2가 실제 종료되었고 EBS·public IPv4·ENI가 남지 않았는지 재조회. 빈 Terraform state만으로 끝내지 않는다. |
| 저장·자동화 | 새 ECR/S3/Logs/Config/Lambda/EventBridge/SQS가 삭제되었는지 또는 정확한 잔존 ID·이유·보관 비용을 기록. 기존 자원은 생성 전 목록과 비교해 유지 확인. |
| 지연 삭제 | Secret은 **7일 복구 기간**, KMS는 **30일 삭제 대기**를 유지한다. ID·예약 시각·실제 삭제 예정일을 기록하고 `PENDING_DELETION`으로 보고한다. 즉시 완전 삭제나 청구 0원을 주장하지 않는다. [Secrets Manager 복구 기간](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html) |
| 권한·외부 자산 | administrator-managed boundary/사용자 정책, 공유 OIDC/recorder, 외부 runner/CodeBuild는 이번 삭제 대상과 별도로 유지한다. 이번 plan에 없던 Inspector/CodeBuild/SNS를 정리 명목으로 변경하지 않는다. |
| 보고 | 실검증 결과, 수동 복구 여부, 생성/정리 시각, 삭제 완료 ID·대기 ID·실패 ID, 백업 위치와 SHA256, 예상 비용을 기록한다. Billing 반영 지연을 고려해 후속 조회하며 계정의 기존 사용료는 분리한다. |

오프라인 검사: `python -m unittest discover -s tests -p test_cleanup_plan.py -v`. 테스트의 account/ID/state는 합성 데이터이며 AWS 삭제 증거가 아니다.
