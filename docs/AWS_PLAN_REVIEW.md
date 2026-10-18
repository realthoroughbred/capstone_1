# 실제 AWS 생성 계획 검토

**승인 전이며 apply는 실행하지 않았습니다.** 계정 `852093844554`, 리전 `ap-northeast-2`, 프로필 `team4`의 실제 AWS API를 사용한 Terraform 계획입니다. 총예산 180,000원은 생성 허가와 별개입니다.

Terraform 결과는 **67 add / 0 change / 0 destroy**입니다. IAM 정책 연결 등도 별도 항목이므로 유료 서비스 67개라는 뜻은 아닙니다. 로컬 state가 없음을 확인했고 이름 조회에서 기존 EKS·ECR·Config recorder·OIDC provider·프로젝트 역할·시크릿·KMS alias가 없었습니다. 기존 기본 VPC는 대상에 포함하지 않습니다.

| 범위 | 생성 계획 |
|---|---|
| 네트워크 | 새 VPC 10.40.0.0/16, 서울 2a/2c subnet 2개, Internet Gateway, route table, flow log; 새 VPC의 default SG 제한 |
| EKS | `team4-eks` 1.35, 관리형 node group 1개, `t3.large` 기본 1대(min 1 / desired 1 / max 2), 노드당 암호화 gp3 20GiB와 public IPv4 |
| 기본 애드온 | VPC CNI `v1.22.4-eksbuild.3`, kube-proxy `v1.35.3-eksbuild.52`, CoreDNS `v1.13.2-eksbuild.51` |
| 이미지·시크릿 | ECR `team4-test`, KMS 키 1개와 alias, 테스트 Secret `team4/demo/token` |
| 복구 | ENI에 연결하지 않는 DemoOnly SG 1개, Config recorder/배달채널/restricted-ssh rule, EventBridge rule, Python Lambda 1개(기본 DRY_RUN) |
| 증적·오류 | S3 증적 버킷 1개, CloudWatch log group 3개, 실패 SQS queue 1개와 alarm 1개 |
| 인증 | IAM 역할 9개, 역할 정책·연결, EKS/GitHub OIDC provider 2개, EKS access entry 2개 |

EKS public API는 사용자가 제공한 관리 PC IPv4 **한 주소의 /32**로 제한합니다. 실제 주소는 Git에서 제외한 tfvars/plan에만 보관합니다. EKS 1.35의 STANDARD_SUPPORT와 2027-03-27 표준 지원 종료를 실제 AWS API로 확인했습니다. NAT Gateway, ALB, Inspector/CodeBuild 대응, SNS topic/subscription은 이번 계획에 없습니다. 승인 전에는 배포 workflow·리소스 생성·SG 위반 주입을 실행하지 않습니다.

## 예상 비용과 유지 조건

[비용 산식과 출처](../COST_AND_CLEANUP.md)를 기준으로, **1노드 8시간 약 8,000원**, **2노드 8시간 약 9,700원**의 예비 예산입니다. 24시간은 각각 약 17,400원/22,500원입니다. 로그·Config·API 등의 임의 준비금, 1 USD=1,500원 및 추가 10% 가정을 포함하며 EC2/gp3의 정확한 서울 단가는 미확정입니다. 확정 견적 또는 상한 보장이 아닙니다. 기존 계정 청구액과 장기 증적 보관료는 별도입니다.

우선 기본 1노드의 최대 8시간 실습을 검토합니다. 추가 노드로 확대하거나 장시간 유지하려면 범위·비용을 다시 확인합니다. 승인 없이 자동 삭제하지 않으므로 8시간이 지나도 유지하면 요금이 계속됩니다. 총 180,000원을 넘는 사용은 허가받은 것으로 간주하지 않습니다.

## 실행 전 남은 조건

- 사용자의 유료 리소스 생성 승인 및 유지·정리 방식 확정.
- [관리자 IAM bootstrap](TEAM4_IAM_PERMISSIONS.md): runtime boundary, provisioning 권한, 새 리소스에만 한정한 default SG/OIDC/network 권한과 검토된 KMS 생성·import. 현재 runtime boundary와 역할들은 존재하지 않습니다. 준비된 기본 정책만으로 한 번에 전체 apply가 가능하다고 보장하지 않습니다.
- bootstrap/import 뒤 state에 맞춰 계획을 다시 생성하고 승인된 자원·비용 범위를 대조합니다. 이 문서의 저장 plan을 그대로 강행하지 않습니다.
- GitHub `aws-demo` 보호 환경·전용 runner·OIDC 연결. ECR/EKS 및 Config 실검증은 이 준비 이후에 수행합니다.
- 실제 SG 복구 시연은 해당 새 DemoOnly SG가 ENI 미연결임을 재확인하고, 공개 TCP22 규칙을 일시 추가하는 실험 범위를 명시적으로 승인받은 뒤 수행합니다.

## 원본 증적

- `evidence/aws/demo-plan.txt`: 실제 plan 명령 출력
- `evidence/aws/demo-plan.json`, `evidence/aws/demo.tfplan`: 기계 판독 및 저장 계획(Git 제외)
- `evidence/aws/preflight.json`, `names-before-plan.json`, `cluster-versions.json`, `instance-types.json`: 실제 읽기 조회

저장 plan SHA256: `fd0f61c5161113c5a71aa672325d260280ac35ce1933fc8bdd316e07158f9318`

## Terraform 관리 주소

- `aws_cloudwatch_event_rule.restricted_ssh[0]` — create
- `aws_cloudwatch_event_target.healing[0]` — create
- `aws_cloudwatch_log_group.cluster` — create
- `aws_cloudwatch_log_group.flow` — create
- `aws_cloudwatch_log_group.healing[0]` — create
- `aws_cloudwatch_metric_alarm.failures[0]` — create
- `aws_config_config_rule.restricted_ssh[0]` — create
- `aws_config_configuration_recorder.demo[0]` — create
- `aws_config_configuration_recorder_status.demo[0]` — create
- `aws_config_delivery_channel.demo[0]` — create
- `aws_default_security_group.closed` — create
- `aws_ecr_lifecycle_policy.test` — create
- `aws_ecr_repository.test` — create
- `aws_eks_access_entry.github_deploy[0]` — create
- `aws_eks_access_entry.operators["team4_operator"]` — create
- `aws_eks_access_policy_association.operators["team4_operator"]` — create
- `aws_eks_addon.dns` — create
- `aws_eks_addon.network["kube-proxy"]` — create
- `aws_eks_addon.network["vpc-cni"]` — create
- `aws_eks_cluster.demo` — create
- `aws_eks_node_group.demo` — create
- `aws_flow_log.demo` — create
- `aws_iam_openid_connect_provider.cluster` — create
- `aws_iam_openid_connect_provider.github[0]` — create
- `aws_iam_role.cluster` — create
- `aws_iam_role.cni` — create
- `aws_iam_role.config[0]` — create
- `aws_iam_role.eso` — create
- `aws_iam_role.flow` — create
- `aws_iam_role.github_deploy[0]` — create
- `aws_iam_role.healing[0]` — create
- `aws_iam_role.kyverno` — create
- `aws_iam_role.node` — create
- `aws_iam_role_policy.config[0]` — create
- `aws_iam_role_policy.eso` — create
- `aws_iam_role_policy.flow` — create
- `aws_iam_role_policy.github_deploy[0]` — create
- `aws_iam_role_policy.healing[0]` — create
- `aws_iam_role_policy.kyverno` — create
- `aws_iam_role_policy_attachment.cluster` — create
- `aws_iam_role_policy_attachment.cni` — create
- `aws_iam_role_policy_attachment.node["AmazonEC2ContainerRegistryPullOnly"]` — create
- `aws_iam_role_policy_attachment.node["AmazonEKSWorkerNodePolicy"]` — create
- `aws_internet_gateway.demo` — create
- `aws_kms_alias.project` — create
- `aws_kms_key.project` — create
- `aws_lambda_function.healing[0]` — create
- `aws_lambda_function_event_invoke_config.healing[0]` — create
- `aws_lambda_permission.healing[0]` — create
- `aws_launch_template.node` — create
- `aws_route_table.public` — create
- `aws_route_table_association.public[0]` — create
- `aws_route_table_association.public[1]` — create
- `aws_s3_bucket.evidence[0]` — create
- `aws_s3_bucket_lifecycle_configuration.evidence[0]` — create
- `aws_s3_bucket_ownership_controls.evidence[0]` — create
- `aws_s3_bucket_policy.evidence[0]` — create
- `aws_s3_bucket_public_access_block.evidence[0]` — create
- `aws_s3_bucket_server_side_encryption_configuration.evidence[0]` — create
- `aws_s3_bucket_versioning.evidence[0]` — create
- `aws_secretsmanager_secret.demo` — create
- `aws_security_group.healing_demo` — create
- `aws_sqs_queue.failures[0]` — create
- `aws_sqs_queue_policy.failures[0]` — create
- `aws_subnet.public[0]` — create
- `aws_subnet.public[1]` — create
- `aws_vpc.demo` — create
