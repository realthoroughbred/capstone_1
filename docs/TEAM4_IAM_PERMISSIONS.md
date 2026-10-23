# team4 AWS 권한 연결 안내

확인된 계정은 `852093844554`, IAM 사용자는 `team4-operator`, 리전은 `ap-northeast-2`입니다. 사용자는 신규 생성·최대 8시간 실검증·ENI 미연결 DemoOnly SG 시험·신규 자원 정리를 승인했습니다. **2026-10-23 관리자 정책 보완 후 신규 자원 67개 생성, EKS 배포 및 실제 Config SG 자동복구를 검증했습니다.** 최종 대조한 정책은 preflight v3, 신규 자원 bootstrap v5, runtime boundary v3입니다. Config `PutEvaluations`는 서울의 Config 역할 하나에만 허용했습니다. 현재 관리자에게 추가 정책 변경을 요청하는 상태가 아니며, 아래는 재현·권한 검토 절차입니다.

관리자는 [구체적인 bootstrap 실행 안내](TEAM4_ADMIN_BOOTSTRAP.md)를 따릅니다. 저장된 실제 plan으로 만든 검토용 JSON은 `generated/admin-bootstrap/initial/`에 있으며, [오프라인 생성기](admin-bootstrap/render.py)가 초기·네트워크·클러스터·노드 단계별 문서를 생성합니다. 이번 실행은 Inspector가 꺼져 있으므로 전체 optional-automation 대신 **Config-only 정책**을 연결합니다. 에이전트가 이 관리자 정책을 AWS에 생성·연결했다는 뜻은 아닙니다.

## 지금 필요한 읽기 권한

먼저 [team4-operator-preflight.json](../iam/team4-operator-preflight.json)만 연결하면 됩니다. 이 정책은 대상 계정의 서울 리전 인프라 메타데이터를 조회하고 현재 Terraform의 AZ 조회를 허용합니다. Secrets Manager 값, SSM 값, S3 객체 내용, DynamoDB 항목, Lambda 환경 변수/코드 다운로드, ECR 이미지 다운로드 권한은 포함하지 않습니다. `ListBucket`은 지정된 증적 버킷의 객체 이름만 조회합니다. IAM 조회는 프로젝트 role/policy 및 지정된 OIDC provider로 제한합니다.

계정 관리자가 다음과 같이 연결합니다.

1. AWS 콘솔 상단 계정 ID가 **852093844554**인지 확인합니다.
2. **IAM → 액세스 관리 → 정책 → 정책 생성 → JSON**에서 위 파일의 전체 JSON을 붙여 넣습니다.
3. **다음 → 정책 이름 `team4-operator-preflight` → 정책 생성**을 선택합니다.
4. **IAM → 사용자 → `team4-operator` → 권한 → 권한 추가 → 권한 추가 → 직접 정책 연결**에서 방금 생성한 정책을 선택하고 연결합니다.
5. 정책 검증에 표시되는 오류는 해결한 뒤 저장합니다. `AdministratorAccess`는 연결하지 않습니다.

관리자가 AWS CLI를 사용한다면 같은 파일로 다음 작업을 할 수 있습니다. 이 명령은 **관리자가 실행하는 권한 변경 작업**이며 이 프로젝트에서 실행한 기록이 아닙니다.

```sh
aws iam create-policy --policy-name team4-operator-preflight \
  --policy-document file://iam/team4-operator-preflight.json
aws iam attach-user-policy --user-name team4-operator \
  --policy-arn arn:aws:iam::852093844554:policy/team4-operator-preflight
```

연결 후 기존 로그인 세션에서 다음 읽기 명령으로 확인합니다. 키나 로그인 토큰을 출력하거나 전달할 필요는 없습니다.

```sh
aws sts get-caller-identity --profile team4 --region ap-northeast-2
aws eks list-clusters --profile team4 --region ap-northeast-2
aws ec2 describe-vpcs --profile team4 --region ap-northeast-2
aws configservice describe-configuration-recorders --profile team4 --region ap-northeast-2
aws ecr describe-repositories --profile team4 --region ap-northeast-2
```

성공 기준은 각 명령의 종료코드 0입니다. 목록이 비어 있어도 정상입니다. 계속 거부되면 SCP, 사용자 boundary, 명시적 Deny 또는 로그인 계정을 함께 확인합니다. 최초 조회 정책은 state 없는 plan 기준이었으며 생성 후 속성 조회도 필요합니다. 현재 파일에는 Project 태그가 있는 VPC의 `ec2:DescribeVpcAttribute`를 추가했습니다. 이번 후속 ZIP은 더 좁은 정확한 신규 VPC ID로 같은 조회를 허용하므로 preflight 정책까지 중복 변경할 필요는 없습니다. IAM 권한 초안은 실제 provider 실행에서 추가 보완이 필요할 수 있습니다.

## 실제 배포 전에 검토할 정책

모든 정책은 같은 계정/리전의 `team4` 프로젝트를 대상으로 합니다. 정책 파일은 IAM 관리형 정책의 6,144자 제한 안에 들어가도록 나누었습니다. 사용자의 작은 inline 정책 대신 **고객 관리형 정책**으로 생성합니다. 관리자가 경계 조각을 병합하거나 ARN을 채운 최종 JSON도 이 제한을 다시 검사해야 합니다. [IAM 정책 크기 제한](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html)을 참조합니다.

| 파일 | 관리형 정책 이름 | 용도 |
|---|---|---|
| [team4-operator-provisioning.json](../iam/team4-operator-provisioning.json) | `team4-operator-provisioning` | 승인된 EKS/VPC/ECR/KMS/로그/Secret metadata 및 프로젝트 자동화 리소스 관리 |
| [team4-runtime-boundary.json](../iam/team4-runtime-boundary.json) | `team4-runtime-boundary` | Terraform이 만드는 모든 IAM role의 최대 권한 경계 |
| [team4-operator-optional-automation.json](../iam/team4-operator-optional-automation.json) | `team4-operator-optional-automation` | Config recorder/rule 및 enhanced ECR scanning을 선택적으로 켤 때만 필요한 리전 전체 API |
| [team4-operator-demo-validation.json](../iam/team4-operator-demo-validation.json) | `team4-operator-demo-validation` | 승인된 합성 test secret의 최초 값 생성·회전·검증만 허용하는 선택 정책 |
| [team4-operator-bootstrap.template.json](../iam/team4-operator-bootstrap.template.json) | 관리자 검토 후 별도 생성 | 새 VPC의 default SG 및 새 클러스터 OIDC issuer의 실제 ARN을 채운 초기 정책 |
| [team4-runtime-network-boundary-fragment.json](../iam/team4-runtime-network-boundary-fragment.json) | 검토 후 runtime boundary에 병합 | CNI role에만 승인한 VPC/subnet/SG의 ENI 작업 상한을 추가하는 조각 |

**배포 정책만 연결한 상태로 전체 apply를 실행할 수는 없습니다.** 다른 리소스에 프로젝트 태그를 붙여 관리 권한을 얻는 경로를 막기 위해 일반 SG/ENI/OIDC 태그 변경 권한을 제공하지 않습니다. 관리자는 승인된 단계별 plan에서 새 VPC·subnet 식별자를 먼저 확인하고, 위 bootstrap template의 default SG ID를 새 VPC의 해당 SG로만 채웁니다. 대안으로 관리자가 그 정확한 SG에 `Project=team4`를 직접 설정할 수 있습니다. 기존 VPC/SG를 재사용하거나 태그를 바꾸는 절차가 아닙니다.

공유 runtime boundary에는 ENI 변경 권한이 없습니다. 새 VPC/subnet/SG 식별자가 나온 뒤 관리자가 네트워크 경계 조각의 모든 `REPLACE_*`를 해당 식별자로 채워 검토·병합해야 CNI 네트워크 작업을 진행할 수 있습니다. 조각은 `team4-vpc-cni` role에만 적용되며, 인스턴스 작업은 `Project=team4` 및 `kubernetes.io/cluster/team4-eks=owned` 태그를 모두 요구합니다. 실제 managed node의 태그를 먼저 확인하며, 없다면 조건을 넓히지 않고 노드 태그 구성을 검토합니다. 이 조각은 EKS control plane/CodeBuild 권한까지 허용하는 정책이 아닙니다. `AmazonEKSClusterPolicy`의 인스턴스·SG·ENI 태깅 등은 관리자가 실제 전용 리소스 ARN을 검토해 별도로 제한해야 합니다. 그 전에는 관련 작업이 거부되는 것이 정상입니다. [AWS CNI IAM 권고](https://aws.github.io/amazon-vpc-cni-k8s/docs/iam-policy.html)와 [EC2 action별 리소스·조건 키](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html)를 참조합니다.

새 EKS control plane의 issuer ID가 확인되면 bootstrap template의 OIDC ARN도 그 ID 하나로 한정합니다. 기존 GitHub OIDC provider는 관리자가 확인하고 `existing_github_oidc_provider_arn`으로 재사용하며 배포 사용자는 수정하지 않습니다. 단계마다 실제 plan을 검토하고, 부작용이나 비용이 있는 생성은 별도 승인 범위에서만 진행합니다.

KMS의 태그를 포함한 최초 `CreateKey`에는 추가 `TagResource` 권한이 필요합니다. 임의의 기존 키를 다시 태깅할 수 있는 권한을 배포 사용자에게 주지 않기 위해 **관리자가 검토된 키 정책과 `Project=team4` 태그로 프로젝트 키를 생성하고, 정확한 키 ID를 `aws_kms_key.project`에 import**하는 bootstrap을 사용합니다. 생성 자체는 비용 승인 이후에만 진행합니다. 배포 정책은 이미 프로젝트 태그가 있는 키의 관리만 허용합니다. [AWS KMS 태그 권한](https://docs.aws.amazon.com/kms/latest/developerguide/tag-permissions.html)을 참조합니다.

관리자는 `team4-runtime-boundary` 정책을 **먼저 생성**합니다. 이를 사용자에게 권한 정책으로 붙이지 않습니다. Terraform 변수에 다음 ARN을 지정하면 각 role의 permissions boundary가 됩니다.

```hcl
aws_account_id = "852093844554"
region = "ap-northeast-2"
project = "team4"
cluster_name = "team4-eks"
iam_permissions_boundary_arn = "arn:aws:iam::852093844554:policy/team4-runtime-boundary"
operator_principal_arns = {
  infra_operator = "arn:aws:iam::852093844554:user/team4-operator"
}
```

`admin_public_cidrs`에는 운영자의 실제 공인 IPv4 `/32`를 별도로 지정하고, `addon_versions`는 서울 리전에서 조회합니다. 배포 role 정책은 위 경계가 있는 `team4-*` role만 만들도록 요구하며, 사용자가 경계를 제거하는 권한은 명시적으로 거부합니다. role의 identity 정책은 이 경계와의 교집합으로 제한됩니다. 리소스 정책이 특정 role session에 직접 권한을 주는 경우 등은 별도 검토해야 하므로 모든 권한 경로가 자동으로 제한된다는 뜻은 아닙니다. [IAM permissions boundary 평가 규칙](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)을 참조합니다. 기존에 `team4-*`라는 이름의 role이 있다면 관리자가 그 소유권과 같은 boundary 적용 여부를 먼저 확인해야 합니다. 기존 unbounded role이 같은 이름 범위에 섞여 있으면 이 보장이 적용되지 않습니다.

경계 생성 후, 관리자는 승인된 배포에 대해서만 preflight 정책에 더해 `team4-operator-provisioning`을 사용자에게 연결합니다. 기본값이 꺼진 Config/Inspector를 켤 때에만 optional 정책을 추가합니다. GitHub OIDC role은 검증된 immutable repository/environment subject만 신뢰합니다. 사용자에게 별도 장기 액세스 키를 만들 필요가 없습니다.

## 범위와 남은 검증

- EKS는 `team4-eks`와 그 nodegroup/addon/access-entry ARN, 프로젝트 ECR 쓰기는 `team4-test`, IAM은 `team4-*` role, S3는 `team4-852093844554-ap-northeast-2-evidence`, Secrets Manager는 `team4/demo/token-*`에 제한됩니다. 기본 조회 정책에는 secret 값 권한이 없습니다. 선택한 demo-validation 정책은 합성 test secret에만 `GetSecretValue`/`PutSecretValue`를 허용합니다. 실제 운영 비밀은 이 경로에 저장하지 않습니다. provisioning의 `UpdateSecret` API는 metadata뿐 아니라 값을 변경할 수도 있어 읽기 전용 권한이 아닙니다.
- 노드는 프로젝트 이미지 외에 AWS 소유 EKS add-on 이미지를 받아야 합니다. 경계에 서울 리전 AWS 계정 `602401143452`의 CNI/CNI-init/network-policy-agent/kube-proxy/CoreDNS 저장소 읽기를 명시했습니다. AWS 저장소에 대한 push는 허용하지 않습니다. [EKS 공식 이미지 레지스트리 목록](https://docs.aws.amazon.com/eks/latest/userguide/add-ons-images.html)을 기준으로 하며 실제 선택한 add-on의 이미지 이름도 배포 전 확인합니다.
- EC2 생성은 요청의 `Project=team4` 태그를, 일반 수정/삭제는 리소스의 같은 태그를 요구합니다. 태그 없는 default SG를 위한 광범위한 예외는 없습니다. 위의 정확한 새 default SG만 대상으로 하는 관리자 bootstrap이 필요합니다. 기존 `Project=team4` 리소스가 있다면 프로젝트 소유권을 먼저 확인합니다.
- EC2 Describe, ECR auth token, Inspector ListFindings, STS 신원 조회 및 일부 생성/목록 API에는 `Resource="*"`가 필요합니다. 공유 경계는 리전 전체 ENI 변경이나 임의 태그 변경을 허용하지 않습니다. 역할별 실제 IAM 정책은 경계보다 더 좁으며, 경계 자체는 권한을 부여하지 않습니다.
- Config recorder/delivery channel과 ECR registry scanning 설정은 계정/리전 단위 설정입니다. optional 정책은 같은 리전의 기존 설정도 바꿀 수 있으므로 기존 조직 설정이 있다면 그대로 적용하지 말고 보존/통합안을 먼저 검토합니다.
- 공급자 관리에 필요한 role 정책, Lambda 환경설정, 로그, KMS grant 같은 API가 포함됩니다. 제공되는 Lambda 환경변수는 리소스 식별자와 dry-run 설정이며 실제 비밀값을 넣지 않습니다. 경계는 현재 no-ALB 구성에 맞춰 ELB/IAM 관리자/SSM 쓰기 권한을 허용하지 않습니다.
- 외부 CodeBuild 프로젝트의 VPC ENI 정책과 private GitHub 연결 사용 권한은 실제 승인된 subnet/connection ARN을 알고 있는 관리자가 별도로 제한해서 설정해야 합니다. 네트워크 경계 조각도 승인한 VPC/subnet으로만 제한하며, 기본 경계는 `Project=team4` 태그가 있는 CodeConnections 사용 범위만 제공합니다. 프로젝트 설정·권한·네트워크는 아직 실제 실행 검증되지 않았습니다.
- JSON 문법과 관리형 정책 크기는 로컬 검사했고 승인된 배포·실복구·정리 API 경로를 실제 검증했습니다. **AWS IAM Access Analyzer policy validation은 별도 미검증**입니다. 관리자는 IAM 정책 생성 화면 또는 `aws accessanalyzer validate-policy --policy-document file://... --policy-type IDENTITY_POLICY`로 추가 검사할 수 있습니다. 이번 경로의 성공이 다른 계정 SCP·경계·서비스 조건에서도 같은 권한이 충분하다는 뜻은 아닙니다.

현재 예산 한도는 **180,000원**이며, 이번에 신규 생성하는 실험 자원의 생성·8시간 검증·정리는 이미 승인되었습니다. 기존 자원의 수정·삭제는 이 범위에 포함되지 않습니다. 정책 연결만으로 유료 리소스가 생성되지는 않으며, 관리자 권한 연결 후 승인된 plan 범위에서 실행을 이어갑니다.
