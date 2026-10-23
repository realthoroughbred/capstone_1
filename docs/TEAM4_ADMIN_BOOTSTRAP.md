# 관리자 실행 안내: 승인된 team4 실환경 검증

사용자는 서울 리전 계정 `852093844554`에서 신규 리소스 생성, 최대 8시간 실검증, **연결되지 않은 `DemoOnly=true` SG의 TCP 22 실험**, 검증 후 이번에 만든 리소스 정리를 승인했습니다. 예산은 **180,000원**입니다. 이 문서는 그 승인 범위를 실행하기 위한 관리자 권한 연결 절차이며 같은 작업의 승인을 다시 요구하는 문서가 아닙니다.

검증에 사용한 로그인 주체는 `arn:aws:iam::852093844554:user/team4-operator`입니다. 원본 승인 plan은 **67 add / 0 change / 0 destroy**입니다. **10월 23일 단계별 관리자 정책 보완을 마치고 전체 생성·EKS 배포·실제 Config SG 자동복구를 검증했습니다.** Config 역할의 `PutEvaluations` 허용을 추가한 runtime boundary v3까지 실제 대조했습니다. 아래는 전체 설치 절차이며 과거 ZIP을 현재 정책에 다시 덮어쓰라는 요청이 아닙니다. 재배포 시에는 새 VPC·SG·시작 템플릿·OIDC ID에 맞게 다시 렌더링해야 합니다.

## 1. 지금 관리자에게 전달할 파일

저장된 plan에서 다음 패키지를 오프라인으로 생성했습니다. 생성기는 AWS를 호출하지 않으며 전체 plan이나 state를 출력 파일에 복사하지 않습니다. `generated/`는 Git에서 제외되어 있으므로 파일 자체를 관리자에게 전달하거나 관리자의 검토 환경에서 재생성합니다.

```sh
python3 docs/admin-bootstrap/render.py \
  --plan evidence/aws/demo-plan.json --phase initial \
  --out generated/admin-bootstrap/initial \
  --new-github-provider-confirmed
```

현재 사전 조사에서 GitHub OIDC provider 목록이 비어 있으므로 마지막 옵션을 사용했습니다. 다시 조사했을 때 provider가 있으면 옵션을 빼고 기존 ARN을 Terraform의 `existing_github_oidc_provider_arn`으로 지정합니다. 기존 provider의 설정이나 권한은 바꾸지 않습니다. 생성기는 출력 폴더가 이미 채워져 있으면 덮어쓰지 않으므로 재생성 시 새로운 출력 경로를 사용합니다.

| 패키지 파일 | 관리자 작업 | 필요한 이유 |
|---|---|---|
| `runtime-boundary.json` | `team4-runtime-boundary` 관리형 정책 생성. 사용자에게 권한 정책으로 연결하지 않음 | Terraform이 만드는 모든 프로젝트 role의 최대 권한 경계 |
| `operator-provisioning.json` | `team4-operator-provisioning` 생성 후 `team4-operator`에 연결 | 프로젝트 리소스 생성·관리·승인된 정리. IAM role은 위 경계가 있어야 생성 가능 |
| `operator-config-only.json` | `team4-operator-config-only` 생성·연결 | 이번 실험의 신규 Config recorder/channel/rule 관리. **Inspector와 ECR registry scanning 변경 권한 제외** |
| `operator-demo-validation.json` | `team4-operator-demo-validation` 생성·연결 | 합성 `team4/demo/token-*` 값의 생성·회전·검증 |
| `operator-evidence-session.json` | `team4-operator-evidence-session` 생성·연결 | 정확한 신규 증적 버킷의 증적 내보내기·버전 정리, Project 태그가 있는 Config rule의 결과 조회·평가 |
| `operator-new-github-provider.json` | `team4-operator-new-github-provider` 생성·연결 | 사전 부재가 확인된 정확한 GitHub issuer 하나의 신규 생성·정리 |
| `kms-create-key.json` | IAM 정책이 아님. 아래 KMS 생성 명령의 입력 | 원본 plan과 동일한 정책·태그를 가진 프로젝트 키를 관리자만 생성 |

각 IAM 문서는 6,144자 이내이며 `manifest.json`에 크기와 SHA-256을 기록합니다. 초기 경계는 3,494자입니다. IAM 콘솔의 정책 생성 → JSON에서 각 파일을 검토하고 오류를 해결합니다. [IAM → 사용자 → team4-operator → 권한 → 권한 추가 → 직접 정책 연결]에서 위의 **operator 정책만** 연결합니다. 이미 연결된 읽기용 `team4-operator-preflight`는 유지합니다. 같은 이름의 기존 정책이 발견되면 새로 덮어쓰지 말고 실제 문서와 이번 작업 소유 여부를 확인합니다.

CLI를 사용하는 관리자의 예시는 다음과 같습니다. `team4-admin`은 관리자가 이미 사용하는 별도 인증 프로필을 뜻하며 이 절차에서 새 관리자 계정을 만들지 않습니다.

```sh
aws sts get-caller-identity --profile team4-admin
aws iam create-policy --profile team4-admin \
  --policy-name team4-runtime-boundary \
  --policy-document file://generated/admin-bootstrap/initial/runtime-boundary.json

for policy_name in provisioning config-only demo-validation evidence-session new-github-provider; do
  aws iam create-policy --profile team4-admin \
    --policy-name "team4-operator-$policy_name" \
    --policy-document "file://generated/admin-bootstrap/initial/operator-$policy_name.json"
  aws iam attach-user-policy --profile team4-admin --user-name team4-operator \
    --policy-arn "arn:aws:iam::852093844554:policy/team4-operator-$policy_name"
done
```

GitHub provider가 기존에 있었다면 마지막 정책은 생성·연결하지 않습니다. Config recorder도 현재는 없지만, 이후 다른 recorder나 조직 설정이 나타나면 이 실험에서 덮어쓰지 않습니다. Config의 일부 관리 API는 리전 단위 `Resource="*"`가 필요하므로, 생성 전 부재 증거와 프로젝트 소유 이름을 함께 확인합니다. 이 실험에서는 Inspector response를 계속 끕니다.

## 2. 관리자 KMS 생성과 운영자 import

KMS는 키를 생성하면서 태그를 붙일 때 아직 존재하지 않는 키에 대한 `kms:TagResource` 권한이 필요합니다. 일반 사용자에게 임의 기존 키를 다시 태깅할 수 있는 권한을 주지 않기 위해 관리자가 **이번 신규 키만** 생성하고, 운영자는 정확한 키 ID를 Terraform state로 import합니다. [AWS KMS 태그 권한](https://docs.aws.amazon.com/kms/latest/developerguide/tag-permissions.html).

```sh
# 관리자: 입력 정책의 account/region/Project 태그를 검토한 후 한 번만 실행
aws kms create-key --profile team4-admin --region ap-northeast-2 \
  --cli-input-json file://generated/admin-bootstrap/initial/kms-create-key.json \
  --output json > generated/admin-bootstrap/kms-created.json
```

`kms-created.json`에는 키 소재가 아닌 생성된 키의 식별자·메타데이터가 있습니다. 관리자는 이 생성 기록과 `KeyMetadata.KeyId`를 운영자에게 전달합니다. 기존 키는 import하지 않습니다. 키에 `Project=team4`, `ManagedBy=Terraform`, `Purpose=StudentDemo` 태그가 있어야 합니다.

```sh
# 운영자: NEW_KMS_KEY_ID에는 위 생성 결과의 실제 UUID만 입력
AWS_PROFILE=team4 terraform -chdir=infra import \
  aws_kms_key.project "$NEW_KMS_KEY_ID"
```

Terraform 변수 `iam_permissions_boundary_arn`은 이미 `arn:aws:iam::852093844554:policy/team4-runtime-boundary`로 지정되어 있습니다. import 후에는 원본 67-add 저장 plan을 바로 apply하지 않고 다음 단계의 plan을 다시 만듭니다. KMS rotation 및 나머지 설정은 현재 Terraform 정의로 관리합니다.

## 3. 신규 네트워크 생성 후 default SG 한 개만 bootstrap

운영자는 초기 권한이 반영된 것을 확인하고 아래 제한된 네트워크 plan을 검토·실행합니다. 이는 이미 승인된 신규 자원의 단계적 생성입니다. `-target`은 식별자 기반 권한을 준비하기 위한 이 초기 절차에만 사용하며, 마지막에는 전체 plan으로 확인합니다.

```sh
AWS_PROFILE=team4 terraform -chdir=infra plan -input=false \
  -target=aws_vpc.demo -target=aws_internet_gateway.demo \
  -target=aws_subnet.public -target=aws_route_table.public \
  -target=aws_route_table_association.public \
  -out=../evidence/aws/stage-network.tfplan
AWS_PROFILE=team4 terraform -chdir=infra apply -input=false \
  ../evidence/aws/stage-network.tfplan
```

관리자와 운영자는 이번 생성 기록에서 새 VPC, 두 subnet, 그 VPC의 default SG를 확인합니다. 사전에 존재했던 `vpc-044ea157cc2bf6edc`는 대상이 아닙니다. 생성기는 이 기존 VPC ID를 거부합니다. 실제 ID를 넣어 아래 정책을 만듭니다.

```sh
python3 docs/admin-bootstrap/render.py --plan evidence/aws/demo-plan.json \
  --phase network --out generated/admin-bootstrap/network \
  --vpc-id "$DEMO_VPC_ID" --default-sg-id "$DEMO_DEFAULT_SG_ID"
```

관리자는 `network/operator-new-resource-bootstrap.json`을 검토하여 `team4-operator-new-resource-bootstrap` 정책으로 생성·연결합니다. 정책은 **정확한 새 default SG 한 개**의 규칙 제거·태그 설정과 **정확한 새 VPC 한 개**의 `ec2:DescribeVpcAttribute` 조회를 허용합니다. DNS 설정 후 Terraform이 속성을 읽는 데 필요합니다. VPC가 자동으로 만든 default SG는 처음에 Project 태그가 없으므로 정확한 ID로 제한합니다. [EC2 IAM 리소스·조건 지원](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html).

10월 23일 부분 생성된 VPC는 Terraform state에 tainted로 기록됐습니다. 권한 연결 후 실제 DNS 속성·태그·CIDR·연결 자원을 확인하고, 재사용 가능할 때 로컬 state의 taint를 해제한 뒤 새 plan을 검토합니다. 원래 저장 plan 재적용이나 자동 교체로 새 ID를 만들지 않습니다.

## 4. Control plane 생성, 정확한 OIDC/CNI 권한 완성

초기 경계에는 [AWS가 문서화한 no-LoadBalancer EKS 최소 권한](https://docs.aws.amazon.com/eks/latest/userguide/cluster-iam-role.html)에 맞춰, `team4-eks-cluster` role이 `Project=team4` 인스턴스에 `kubernetes.io/cluster/team4-eks` 키만 태깅할 수 있는 문장이 추가되어 있습니다. 지역 전체 SG/ENI 태그 변경이나 ELB 생성 권한을 추가하지 않습니다. EKS service-linked role은 별도의 AWS 관리 주체입니다.

```sh
AWS_PROFILE=team4 terraform -chdir=infra plan -input=false \
  -target=aws_eks_cluster.demo -out=../evidence/aws/stage-cluster.tfplan
AWS_PROFILE=team4 terraform -chdir=infra apply -input=false \
  ../evidence/aws/stage-cluster.tfplan
aws eks describe-cluster --profile team4 --region ap-northeast-2 \
  --name team4-eks \
  --query 'cluster.{Arn:arn,Subnets:resourcesVpcConfig.subnetIds,Vpc:resourcesVpcConfig.vpcId,NodeSG:resourcesVpcConfig.clusterSecurityGroupId,Issuer:identity.oidc.issuer}'
```

출력의 VPC/subnet이 3단계 신규 자원과 일치하는지 확인합니다. `NodeSG`는 EKS가 이번 클러스터에 생성한 SG이며 default SG와 다릅니다. 아래는 이 실제 식별자를 넣는 명령입니다.

```sh
python3 docs/admin-bootstrap/render.py --plan evidence/aws/demo-plan.json \
  --phase cluster --out generated/admin-bootstrap/cluster \
  --vpc-id "$DEMO_VPC_ID" --default-sg-id "$DEMO_DEFAULT_SG_ID" \
  --subnet-a-id "$DEMO_SUBNET_A_ID" --subnet-c-id "$DEMO_SUBNET_C_ID" \
  --node-sg-id "$DEMO_NODE_SG_ID" --issuer-url "$DEMO_OIDC_ISSUER_URL"
```

관리자는 생성된 두 정책을 검토합니다. `runtime-boundary.json`은 기존 제한에 **정확한 CNI role + 새 VPC/subnet/SG**의 ENI 작업을 더합니다. `operator-new-resource-bootstrap.json`은 정확한 신규 default SG와 해당 클러스터 OIDC issuer만 포함합니다. 관리자는 동일한 이름의 관리형 정책에 새 버전을 만들고 기본 버전으로 지정합니다.

```sh
aws iam create-policy-version --profile team4-admin --set-as-default \
  --policy-arn arn:aws:iam::852093844554:policy/team4-runtime-boundary \
  --policy-document file://generated/admin-bootstrap/cluster/runtime-boundary.json
aws iam create-policy-version --profile team4-admin --set-as-default \
  --policy-arn arn:aws:iam::852093844554:policy/team4-operator-new-resource-bootstrap \
  --policy-document file://generated/admin-bootstrap/cluster/operator-new-resource-bootstrap.json
```

관리형 정책 크기는 생성기가 다시 검사합니다. Statement의 선택적 `Sid`만 제거해 크기를 줄이며 action/resource/condition을 생략하지 않습니다. IAM policy version이 5개에 도달했다면 이 프로젝트의 오래된 비기본 버전만 관리자가 검토하여 정리합니다. CNI는 노드의 Project 및 cluster-owned 태그를 요구하므로 실제 노드 태그도 확인합니다. 이 절차는 외부 CodeBuild/VPC 접근을 허용하지 않습니다.

## 5. 노드 시작과 S3 후속 조회 권한

10월 23일 전체 apply에서 태그를 포함한 launch template의 노드 시작 검사와 S3 후속 조회가 거부됐다. [EKS 문서](https://docs.aws.amazon.com/eks/latest/userguide/launch-templates.html)에 따라 호출자에게 `ec2:RunInstances`와 시작 시 태그 권한이 필요하다. Terraform S3 버킷 조회에는 초기 `s3:*Bucket*`에 포함되지 않는 `s3:GetAccelerateConfiguration`, `s3:GetReplicationConfiguration`도 필요하다.

```sh
python3 docs/admin-bootstrap/render.py --plan evidence/aws/demo-plan.json \
  --phase nodes --out generated/admin-bootstrap/nodes \
  --vpc-id "$DEMO_VPC_ID" --default-sg-id "$DEMO_DEFAULT_SG_ID" \
  --subnet-a-id "$DEMO_SUBNET_A_ID" --subnet-c-id "$DEMO_SUBNET_C_ID" \
  --node-sg-id "$DEMO_NODE_SG_ID" --issuer-url "$DEMO_OIDC_ISSUER_URL" \
  --launch-template-id "$DEMO_LAUNCH_TEMPLATE_ID"
```

관리자는 `operator-new-resource-bootstrap.json`으로 기존 **team4-operator-new-resource-bootstrap 하나만** 전체 교체하고 기본 버전으로 저장한다. `runtime-boundary.json`은 이전 클러스터 단계와 같아 다시 적용하지 않는다. 시작 권한은 실제 새 template·서브넷·EKS SG, `t3.large`, Project/ManagedBy 태그로 제한한다. 거부 메시지 진단용 `sts:DecodeAuthorizationMessage`는 읽기 전용이며 리소스 단위 제한을 지원하지 않는다. 기존 VPC/DNS/기본 SG/OIDC 권한은 유지한다.

이번 전달 파일은 `generated/team4-node-s3-admin-20261023.zip`이며 안의 `먼저읽기.txt`와 동일 정책명 JSON을 사용한다. 새 IAM 정책·KMS 키·사용자 연결은 필요 없다. 버킷은 이미 생성됐으므로 재시도 전 실제 태그·소유권·상태를 확인하고 필요한 경우 로컬 taint만 해제하여 불필요한 교체를 방지한다.

## 6. 전체 배포, 검증, 정리

운영자는 이제 전체 plan을 다시 확인하여 이번 생성·import한 자원 외의 수정이나 삭제가 없는지 대조하고 적용합니다. SG 실험은 정확한 생성 ID, `Project=team4`, `DemoOnly=true`, ENI 미연결을 다시 확인한 뒤 수행합니다. Lambda는 평소 `DRY_RUN=true`를 유지하고 승인된 해당 실험에만 변경합니다. 합성 secret 검증 과정에서 값 자체를 로그나 문서에 출력하지 않습니다.

검증 종료 후에는 이번 작업의 생성 전 부재·생성 기록·실제 ID를 대조하여 신규 자원만 정리합니다. Config recording과 이벤트를 멈춘 뒤 필요한 증적을 내보내고, 해당 증적 버킷의 객체·이전 버전 및 해당 ECR repository의 이미지를 정리해야 `force_destroy=false`/`force_delete=false` 자원을 삭제할 수 있습니다. 증적용 선택 정책은 이 정확한 버킷에만 내보내기·버전 삭제를 허용합니다. Terraform graph는 node group 및 cluster를 네트워크보다 먼저 정리합니다.

Secrets Manager는 **7일 복구 대기**, KMS는 **30일 삭제 대기**가 있으므로 해당 상태는 즉시 물리 삭제와 구분해 보고합니다. 이번에 생성한 GitHub OIDC provider와 관리자 bootstrap 정책도 별도 생성 장부에 포함합니다. 기존 preflight 정책·기존 VPC·기존 OIDC provider는 정리 대상이 아닙니다. IAM 정책/경계 정리는 role과 해당 정책의 연결이 모두 사라진 후 관리자가 맡습니다. 정리 승인은 이미 주어졌으며 추가 승인을 요구하지 않습니다.

이 문서의 생성기는 JSON 생성·크기 검사를 수행했지만 AWS IAM 실제 평가를 대체하지 않습니다. 관리자는 IAM 콘솔 또는 [Access Analyzer ValidatePolicy](https://docs.aws.amazon.com/access-analyzer/latest/APIReference/API_ValidatePolicy.html)로 검증할 수 있습니다. 실행 중 거부가 발생하면 거부된 action과 정확한 이번 신규 ARN을 근거로 수정하며 전체 관리자 권한이나 기존 리소스 권한 확대를 대안으로 사용하지 않습니다.
