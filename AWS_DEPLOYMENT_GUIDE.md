# AWS 배포 및 실환경 검증 절차

**2026-10-23 실검증 결과:** 승인된 신규 자원 67개를 생성하고 EKS 1.35와 t3.large 1노드에서 실제 검증을 마쳤다. [GitHub 배포 run](https://github.com/realthoroughbred/capstone_1/actions/runs/39955813458)의 OIDC 인증·ECR 업로드·cosign 서명·SBOM·Pod digest·HTTP 검증이 통과했다. NetworkPolicy, ESO rotation, Kyverno 미서명 이미지 거부, Argo CD 정책 복구도 통과했다. Config→EventBridge→Lambda SG 자동복구는 주입부터 규칙 제거 관측까지 123.473초였고 정상 재평가를 확인했다. 정리 완료 여부는 [현재 상태](IMPLEMENTATION_STATUS.md)를 따른다.

WSL `team4` profile로 계정 `852093844554`의 `team4-operator` 신원을 재확인했다. 최초 승인 계획 **67 add / 0 change / 0 destroy**는 [생성 계획 검토](docs/AWS_PLAN_REVIEW.md)에 보존했다. 실제 신규 ID 장부는 `evidence/aws/full-created-ledger-20261023.json`이다. 부분 실패 당시의 47개·62개 장부는 과거 기록이며 최종 정리에 재사용하지 않는다. 아래는 재현 절차로, 재배포 시 새 기간·비용·승인과 현재 state를 확인한다.

사용자가 정한 **총예산은 180,000원**이다. 기본 1노드·최대 8시간 실검증, ECR/EKS 배포, ENI 미연결 DemoOnly SG의 TCP22 임시 공개·자동복구 시험 및 신규 자원 정리는 **이미 승인됐다**. 승인 기록은 `evidence/aws/authorization.json`에 보관했다. KMS 생성 10월 23일 19:40 KST부터 보수적으로 계산한 8시간 창은 **10월 24일 03:40 KST**까지다. 이번 신규 자원 정리는 삭제 후 AWS 조회까지 완료했다. KMS와 Secret은 각각 30일·7일 복구 기간의 삭제 예약이며 자세한 결과는 비용·정리 보고서를 따른다. 관리 PC 공인 IP 변경은 사용자가 승인했고 현재 IPv4 한 개(`/32`)를 Git 제외 tfvars에 반영했다. 기존 자원 변경이나 Inspector/CodeBuild 확장은 승인 범위 밖이다.

기본 설계는 서울 리전 `ap-northeast-2`, EKS `team4-eks` 1.35, `t3.large` 노드 1대(min=1, desired=1, max=2), 암호화된 gp3 20 GiB이다. 두 public subnet과 Internet Gateway를 사용하며 NAT Gateway와 ALB는 만들지 않는다. 노드는 public IPv4를 사용하고 SSH를 열지 않는다. EKS public API는 승인된 운영자·배포 runner의 `/32`만 허용하고 private API도 켠다. 실제 용량·가용 버전·비용은 계정 조회와 최종 plan으로 확인한다. 상세 설계는 [infra-notes](docs/infra-notes.md), 예산과 보존 조건은 [COST_AND_CLEANUP](COST_AND_CLEANUP.md)을 따른다.

## 1. 현재 IAM 로그인과 권한 보완

현재 사용한 방식은 `aws login --remote`로 IAM 사용자 콘솔 세션을 임시 CLI 자격 증명으로 연결하는 방식이다. **IAM Identity Center SSO가 아니므로 `aws configure sso`나 `aws sso login`으로 바꾸지 않는다.** 장기 access key를 만들거나 root 계정으로 로그인할 필요도 없다. [AWS 콘솔 기반 CLI 로그인](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html).

계정 관리자는 IAM → **Users → team4-operator → Permissions**에서 현재 정책, 그룹, permissions boundary를 확인한다. SCP 등 상위 명시적 거부가 있으면 identity policy만 추가해서 해결되지 않는다. 초기에 실패했지만 지금 통과한 API는 `eks:ListClusters`, `ec2:DescribeVpcs`, `config:DescribeConfigurationRecorders`, `ecr:DescribeRepositories`, `iam:ListOpenIDConnectProviders`다. 이 5개를 허용하는 것만으로 전체 Terraform plan/apply 권한이 완성되지는 않는다.

관리자에게 요청한 읽기 정책과 콘솔 순서는 [TEAM4_IAM_PERMISSIONS](docs/TEAM4_IAM_PERMISSIONS.md)에 있다. 현재 기본 조회 재검증은 통과했다. provisioning 정책·런타임 boundary·선택 자동화 정책은 따로 검토하며, 읽기 성공이나 정책 파일 준비를 실제 쓰기 권한·생성 승인으로 기록하지 않는다.

사전 조회, 인프라 provisioner, 런타임 권한을 분리한다. 정책 초안은 계정 관리자가 기존 공유 리소스·SCP·permissions boundary와 함께 검토하며 `PowerUserAccess`만으로 IAM 역할 생성·PassRole이 충족된다고 가정하지 않는다. 런타임 역할에 관리자 권한을 부여하지 않는다. 조직이 나중에 SSO로 전환하기로 정한 경우에만 별도 permission set 생성 → 사용자/그룹의 AWS 계정 할당 → SSO profile 설정을 따른다. [AWS permission set](https://docs.aws.amazon.com/singlesignon/latest/userguide/howtocreatepermissionset.html), [계정 할당](https://docs.aws.amazon.com/singlesignon/latest/userguide/assignusers.html).

| 실행 주체 | 필요한 범위 / 구현 경계 |
| --- | --- |
| Terraform provisioner | 프로젝트 EC2/VPC/SG, EKS·access entry·addon, ECR, IAM 역할/OIDC, KMS, Logs, Secrets Manager 생성·조회·변경. 옵션 활성화 시 Config, Lambda, EventBridge, S3, SQS, DynamoDB, ECR enhanced scanning도 필요. `iam:PassRole`은 해당 서비스 역할, 서비스 연결 역할 생성은 필요한 AWS 서비스로 제한한다. 실제 정책은 `infra/*.tf`와 승인된 plan에서 확정한다. |
| Kubernetes 초기 운영자 | `operator_principal_arns`의 영구 IAM role/user ARN에 EKS cluster-admin access entry. STS session ARN을 넣지 않는다. 초기 controller/RBAC 설치 권한이다. |
| GitHub 배포 역할 | OIDC의 정확한 저장소·`aws-demo` environment 신뢰, 지정 ECR push와 지정 EKS DescribeCluster. Kubernetes 권한은 `team4:deploy` 그룹의 `demo` namespace RBAC로 분리한다. |
| 노드 / VPC CNI | 노드는 EKS worker와 ECR pull 역할, CNI는 `kube-system/aws-node` 전용 IRSA. |
| ESO / Kyverno | ESO는 지정 secret 1개의 읽기와 해당 KMS decrypt, Kyverno admission은 지정 ECR의 서명 조회용 pull 권한. |
| SG Lambda | 계정·리전·태그·SG ID·미부착 ENI 확인 후 지정 demo SG의 ingress revoke만 허용. 증적·로그·실패 큐 권한을 별도로 부여한다. |
| Inspector Lambda / CodeBuild | Lambda는 finding/승인/이미지/project 설정 조회, 영구 dedup 기록, 지정 project 시작. worker는 승인 읽기·ECR pull·증적 기록과 `team4:image-remediator` RBAC의 `demo/server` patch만 수행한다. 승인 파라미터 변경 권한은 없다. |

## 2. CLI 로그인과 읽기 전용 사전 조사

이 문서의 셸은 **Ubuntu/WSL Bash**, 저장소 루트 기준이다. 확인된 로그인은 WSL 안에 있으므로 Windows AWS CLI에 같은 profile이 있다고 가정하지 않는다. 정상 세션은 그대로 쓰고, 만료되었을 때 다음 로그인 명령으로 갱신한다.

```bash
aws login --remote --profile team4 --region ap-northeast-2
aws sts get-caller-identity --profile team4 --region ap-northeast-2
export AWS_PROFILE=team4 AWS_REGION=ap-northeast-2 AWS_PAGER=""
```

CLI가 표시한 URL을 브라우저에서 열고 `team4-operator` 세션을 선택한 뒤, 표시된 인증 코드를 **그 CLI 입력창에만** 넣는다. STS의 Account가 `852093844554`와 다르면 진행하지 않는다. 인증 코드·임시 토큰·`.aws/login/cache`를 채팅·저장소·증적에 복사하지 않는다. 로그인 성공은 서비스 권한이나 생성 승인을 뜻하지 않는다. [AWS login 명령](https://docs.aws.amazon.com/cli/latest/reference/login/).

Terraform AWS provider와 Terraform 자체의 S3 backend는 인증 구현이 다르다. 현재 `team4` 프로필로 AWS provider의 실제 plan은 검증했으며 원격 S3 backend 인증은 검증하지 않았다. 도구가 `login_session`을 읽지 못할 때만 WSL의 `~/.aws/config`에 다음 **별도** profile을 추가하고 `AWS_PROFILE=team4-tools`로 도구를 실행한다. 기존 `team4` profile을 덮어쓰지 않는다. credential process가 출력하는 비밀은 SDK만 소비하도록 하며 export 명령을 터미널이나 파일에 직접 출력하지 않는다. [AWS 공식 호환 방법](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html).

```ini
[profile team4-tools]
credential_process = aws configure export-credentials --profile team4 --format process
region = ap-northeast-2
```

**기본 조회 성공 후 기존 리소스와 공유 설정을 조사**한다. 아래 사전 검사 5개는 통과했으며 추가 inventory와 실제 plan에 필요한 조회는 계속 확인한다. 결과는 접근 통제된 `evidence/aws/` 등에 보관한다. 다른 API의 AccessDenied를 빈 목록으로 간주하거나 태그 검색만으로 모든 기존 리소스를 찾았다고 판단하지 않는다.

```bash
python3 scripts/aws-preflight.py --profile team4 --account 852093844554 --region ap-northeast-2
# 위 5개 기본 조회와 별도로 아래 추가 inventory도 확인한다.
aws eks list-clusters
aws ec2 describe-vpcs
aws ec2 describe-nat-gateways
aws ec2 describe-addresses
aws elbv2 describe-load-balancers
aws configservice describe-configuration-recorders
aws configservice describe-configuration-recorder-status
aws configservice describe-delivery-channels
aws ecr get-registry-scanning-configuration
aws ecr describe-repositories
aws iam list-open-id-connect-providers
aws secretsmanager list-secrets --query 'SecretList[].{Name:Name,ARN:ARN}'
aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=team4
```

기존 Config recorder가 있다면 이름만 입력하는 것으로 충분하지 않다. 실행 상태와 `AWS::EC2::SecurityGroup` 기록 범위·전달 설정을 확인하고 조직 recorder를 덮어쓰지 않는다. 없을 때만 승인된 plan에서 `create_config_recorder=true`를 검토한다. ECR registry scanning은 리전 공유 설정이므로 기존 repository 필터를 보존할 방법이 확정되기 전에는 Inspector 옵션을 켜지 않는다. 기존 GitHub OIDC provider도 재사용 여부를 확인한다. 노드용 EC2 quota, EKS 1.35 제공 여부, IP/Pod 용량을 함께 확인한다.

## 3. 구체적인 plan을 만든 뒤 생성 승인

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
# 계정 852093844554, 운영자 IAM ARN, 실제 public IPv4 /32와 승인된 boundary를 편집한다.
bash scripts/05-addon-versions.sh
terraform -chdir=infra init -lockfile=readonly
terraform -chdir=infra validate
terraform -chdir=infra plan -out=reviewed.tfplan
terraform -chdir=infra show -no-color reviewed.tfplan
```

`05-addon-versions.sh`는 실제 EKS API에서 호환 addon 버전을 조회하여 `infra/addons.auto.tfvars.json`을 만든다. 조회 실패 시 테스트용 버전을 대신 쓰지 않는다. 현재 사용자를 bootstrap 운영자로 승인한다면 `operator_principal_arns`에는 `arn:aws:iam::852093844554:user/team4-operator`를 넣는다. cluster creator의 자동 admin 부여는 꺼져 있으므로 이 목록에서 운영자를 빠뜨리면 안 된다. 별도 역할로 전환한다면 실제 영구 IAM role ARN과 권한을 다시 검토한다.

제공된 provisioning 정책을 사용하려면 관리자가 먼저 `team4-runtime-boundary`를 만들고 `iam_permissions_boundary_arn="arn:aws:iam::852093844554:policy/team4-runtime-boundary"`를 지정해야 한다. 해당 정책은 이 경계가 있는 프로젝트 role 생성만 허용한다. 새 VPC·시작 템플릿·CNI의 실제 ID를 반영한 단계별 bootstrap 정책과 Config의 `PutEvaluations` 허용이 필요하다. 이번 배포에서 해당 API 경로를 실제 검증했으며 자세한 범위는 [권한 문서](docs/TEAM4_IAM_PERMISSIONS.md)와 [infra-notes](docs/infra-notes.md)를 따른다. 다른 계정·새 ID에서의 권한 성공을 보장하지 않는다.

모듈의 기본값은 자동화 옵션이 꺼져 있다. 이번에 실제 검토·승인된 plan은 `enable_self_healing=true`, `healing_dry_run=true`, `create_config_recorder=true`, `enable_github_deploy=true`, `enable_inspector_response=false`다. SG 시험 단계에서 승인 범위에 따라 dry run을 해제한다. plan/state에는 민감한 값이 포함될 수 있으므로 Git에 넣지 않는다. 협업 시 잠금과 암호화가 있는 승인된 state 저장소를 먼저 준비한다.

**계정·리전·생성/교체/삭제 목록·총예산 180,000원 내 비용 및 유지 기간을 확인한 명시적 생성 승인 뒤에만** 다음 명령을 실행한다. 오래된 plan이나 변경된 입력은 다시 검토한다.

```bash
terraform -chdir=infra apply reviewed.tfplan
terraform -chdir=infra output
aws eks update-kubeconfig --name team4-eks --region ap-northeast-2 --alias team4-eks
kubectl --context team4-eks get nodes -o wide
kubectl --context team4-eks get pods -A
```

## 4. 애플리케이션·보안 기능·복구 실험

초기 운영자가 controller와 namespaced RBAC를 설치한다. 다음 명령은 클러스터를 변경하므로 승인된 배포 단계에서 실행한다.

```bash
bash scripts/07-install-security-addons.sh team4-eks all
bash scripts/12-configure-eks-security.sh
```

Secrets Manager 관리자가 콘솔에서 `terraform -chdir=infra output -raw demo_secret_arn`이 가리키는 **전용 demo secret**에 `{"token":"새로 생성한 실습 전용 값"}` 형태의 값을 넣는다. 실제 운영 비밀을 사용하지 않는다. Terraform은 secret 컨테이너만 만들며 값은 state에 넣지 않는다. 이 값 입력 역시 승인된 배포 범위에서 수행하고 화면·로그에 값을 남기지 않는다. 제공된 provisioner 정책에 secret 값 접근이 자동 포함된다고 가정하지 않는다.

GitHub의 `aws-demo` environment 승인자·main 전용 정책·격리 runner·변수는 [GITHUB_SETUP](docs/GITHUB_SETUP.md)을 적용한다. Terraform의 `github_deploy_role_arn`, `repository_url`과 승인 계정 ID를 사용한다. 배포 workflow는 digest·cosign·스캔을 검증하고 실제 ready Pod의 runtime digest까지 확인한다. `deployed-image.txt`나 빌드 시작만으로 배포 성공을 기록하지 않는다.

서명된 workload 배포 후 아래 검사를 수행한다. `09`의 `--rotate-demo`는 실제 demo secret 값을 교체하므로 별도 승인된 회전 실험에서만 추가한다. unsigned 이미지 차단 검사는 실제 존재하는 unsigned ECR digest를 `UNSIGNED_TEST_IMAGE`에 지정해야 하며, 없을 때의 `NOT_TESTED`를 통과로 바꾸지 않는다. controller 설치 성공과 실제 secret 동기화·정책 차단은 별도 증적이다.

```bash
export ESO_ROLE_ARN="$(terraform -chdir=infra output -raw eso_role_arn)"
export DEMO_SECRET_ARN="$(terraform -chdir=infra output -raw demo_secret_arn)"
bash scripts/09-eso-test.sh team4-eks aws
bash scripts/10-admission-test.sh team4-eks
bash scripts/08-network-policy-test.sh team4-eks
```

SG 복구는 기본 `healing_dry_run=true`이다. 활성화 후에도 변경 없이 검사하며, 별도로 승인된 실험에서만 false로 바꾸고 [SELF_HEALING_REPORT](SELF_HEALING_REPORT.md)의 demo CLI를 실행한다. 실제 Config NON_COMPLIANT → Lambda 복구 로그 → 규칙 제거 → COMPLIANT를 모두 수집해야 한다.

Inspector는 기본 비활성이다. **외부의 신뢰할 수 있는 CodeBuild project**를 먼저 준비해야 한다. Terraform은 project나 NAT를 만들지 않는다. EKS에 도달하는 고정 egress `/32` 또는 승인된 private 경로와 AWS API·GitHub·서명/스캔 도구·취약점 DB 접근이 필요하다. VPC CodeBuild는 public subnet에서도 public IP를 받지 않아 IGW만으로 인터넷에 나갈 수 없다. VPC 연결 시 관리자가 별도로 승인된 subnet 범위의 ENI 권한을 exported role에 추가해야 하며, private GitHub source 연결 권한도 별도다. EKS API를 `0.0.0.0/0`로 넓혀 해결하지 않는다.

`remediation_codebuild_contract` 출력의 role·검토된 40자리 source SHA·buildspec·환경·KMS/artifact 설정을 적용하고 서명·스캔을 통과한 replacement digest를 만료 24시간 이내의 보호된 SSM 승인에 등록한다. 자세한 계약은 [automation/README](automation/README.md)와 [infra-notes](docs/infra-notes.md)에 있다. 아직 이 연결, IAM, actual finding, rollout은 실환경에서 검증되지 않았다.
