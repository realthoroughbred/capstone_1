# team4 AWS 권한 연결 안내

확인된 계정은 `852093844554`, IAM 사용자는 `team4-operator`, 리전은 `ap-northeast-2`입니다. `aws login --remote --profile team4` 로그인과 STS 신원 확인은 성공했습니다. 현재 EKS 목록, VPC 조회, AWS Config recorder 조회, ECR repository 조회가 AccessDenied로 차단되어 실제 계정 조사와 plan을 진행하지 못합니다. 아래 정책은 검토용으로 준비한 파일이며, AWS에 생성하거나 연결하지 않았습니다.

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

성공 기준은 각 명령의 종료코드 0입니다. 목록이 비어 있어도 정상입니다. 계속 거부되면 조직 SCP, 사용자 permissions boundary, 다른 정책의 명시적 Deny 또는 로그인 계정을 함께 확인해야 합니다. 에이전트는 연결 확인 후 기존 리소스 중복 여부, add-on 버전, Terraform 실제 plan과 비용 영향을 이어서 검토합니다. 현재 state가 없는 새 배포 plan에 필요한 조회를 준비했으며, 기존 Lambda 등이 state에 있다면 환경설정 조회가 필요하므로 아래 배포 정책 검토가 추가로 필요할 수 있습니다.

## 실제 배포 전에 검토할 정책

모든 정책은 같은 계정/리전의 `team4` 프로젝트를 대상으로 합니다. 정책 파일은 IAM 관리형 정책의 6,144자 제한 안에 들어가도록 나누었습니다. 사용자의 작은 inline 정책 대신 **고객 관리형 정책**으로 생성합니다.

| 파일 | 관리형 정책 이름 | 용도 |
|---|---|---|
| [team4-operator-provisioning.json](../iam/team4-operator-provisioning.json) | `team4-operator-provisioning` | 승인된 EKS/VPC/ECR/KMS/로그/Secret metadata 및 프로젝트 자동화 리소스 관리 |
| [team4-runtime-boundary.json](../iam/team4-runtime-boundary.json) | `team4-runtime-boundary` | Terraform이 만드는 모든 IAM role의 최대 권한 경계 |
| [team4-operator-optional-automation.json](../iam/team4-operator-optional-automation.json) | `team4-operator-optional-automation` | Config recorder/rule 및 enhanced ECR scanning을 선택적으로 켤 때만 필요한 리전 전체 API |

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

`admin_public_cidrs`에는 운영자의 실제 공인 IPv4 `/32`를 별도로 지정하고, `addon_versions`는 서울 리전에서 조회합니다. 배포 role 정책은 위 경계가 있는 `team4-*` role만 만들도록 요구하며, 사용자가 경계를 제거하는 권한은 명시적으로 거부합니다. role의 inline 정책을 임의로 바꾸더라도 경계 밖 권한을 획득하지 못하도록 설계했습니다. 기존에 `team4-*`라는 이름의 role이 있다면 관리자가 그 소유권과 같은 boundary 적용 여부를 먼저 확인해야 합니다. 기존 unbounded role이 같은 이름 범위에 섞여 있으면 이 보장이 적용되지 않습니다.

경계 생성 후, 관리자는 승인된 배포에 대해서만 preflight 정책에 더해 `team4-operator-provisioning`을 사용자에게 연결합니다. 기본값이 꺼진 Config/Inspector를 켤 때에만 optional 정책을 추가합니다. GitHub OIDC role은 검증된 immutable repository/environment subject만 신뢰합니다. 사용자에게 별도 장기 액세스 키를 만들 필요가 없습니다.

## 범위와 남은 검증

- EKS는 `team4-eks`와 그 nodegroup/addon/access-entry ARN, ECR은 `team4-test`, IAM은 `team4-*` role, S3는 `team4-852093844554-ap-northeast-2-evidence`, Secrets Manager는 `team4/demo/token-*`에 제한됩니다. Secret 값 읽기는 배포 사용자에게 허용하지 않으며, 정확한 test secret을 읽는 ESO role에만 별도 부여합니다.
- EC2 생성은 요청의 `Project=team4` 태그를, 일반 수정/삭제는 리소스의 같은 태그를 요구합니다. 다만 VPC가 자동 생성한 **default security group은 처음에 태그가 없고 Terraform이 규칙을 먼저 제거**합니다. 따라서 `DefaultSGAdoption` 문에는 서울 리전/해당 계정 SG의 ingress/egress 제거와 태그 설정 권한이 포함됩니다. 이는 기존 SG에도 영향을 줄 수 있는 초기 bootstrap 예외입니다. 관리자는 이 문을 명시적으로 검토하고, 새 VPC 생성 후 실제 demo default SG ARN으로 좁혀야 합니다. 실행 대상은 Terraform이 새로 만든 VPC의 default SG입니다.
- EC2 Describe, ECR auth token, Inspector ListFindings, STS 신원 조회 및 일부 생성/목록 API에는 `Resource="*"`가 필요합니다. 런타임 경계의 CNI ENI 작업도 서울 리전으로 한정하지만 네트워크 인터페이스를 다루는 강한 권한입니다. 역할별 실제 IAM 정책은 경계보다 더 좁으며, 경계 자체는 권한을 부여하지 않습니다.
- Config recorder/delivery channel과 ECR registry scanning 설정은 계정/리전 단위 설정입니다. optional 정책은 같은 리전의 기존 설정도 바꿀 수 있으므로 기존 조직 설정이 있다면 그대로 적용하지 말고 보존/통합안을 먼저 검토합니다.
- 공급자 관리에 필요한 role 정책, Lambda 환경설정, 로그, KMS grant 같은 API가 포함됩니다. 제공되는 Lambda 환경변수는 리소스 식별자와 dry-run 설정이며 실제 비밀값을 넣지 않습니다. 경계는 현재 no-ALB 구성에 맞춰 ELB/IAM 관리자/SSM 쓰기 권한을 허용하지 않습니다.
- 외부 CodeBuild 프로젝트의 VPC ENI 정책과 private GitHub 연결 사용 권한은 실제 승인된 subnet/connection ARN을 알고 있는 관리자가 별도로 제한해서 설정해야 합니다. 경계는 서울 리전 ENI 작업과 `Project=team4` 태그가 있는 CodeConnections 사용 범위를 제공합니다. 프로젝트 설정·권한·네트워크는 아직 실제 실행 검증되지 않았습니다.
- JSON 문법과 관리형 정책 크기는 로컬 검사합니다. **AWS IAM Access Analyzer policy validation, IAM 실제 평가 및 Terraform apply는 아직 검증하지 않았습니다.** 관리자는 IAM 정책 생성 화면 또는 `aws accessanalyzer validate-policy --policy-document file://... --policy-type IDENTITY_POLICY`로 AWS 검증을 수행할 수 있습니다. 실제 plan/API가 추가 action을 요구하면 거부된 action과 ARN에 맞춰 수정하며 관리자 전체 권한으로 대체하지 않습니다.

정책에 삭제 API가 있어도 리소스 삭제 승인을 뜻하지 않습니다. 실제 생성은 사용자가 승인한 비용/plan 범위에서만 진행하고, 삭제는 별도 명시적 승인 후 수행합니다. 현재 예산 한도는 **180,000원**이며 정책 연결만으로 유료 리소스는 생성되지 않습니다.
