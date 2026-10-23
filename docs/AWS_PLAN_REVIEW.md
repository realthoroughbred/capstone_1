# 실제 AWS 생성 계획 검토

**신규 생성·최대 8시간 실검증·SG 시험 및 신규 자원 정리가 승인됐으며, 10월 23일 단계별 apply를 실행했습니다.** VPC·EKS 제어 영역 ACTIVE·CNI/kube-proxy·ECR·OIDC 등을 확인했고 현재 Terraform 관리 자원은 47개입니다. 전체 apply는 노드 시작과 S3 후속 조회 권한에서 부분 실패했습니다. 노드 0개, Config/Lambda·ECR 이미지·워크로드 검증은 미완료입니다. 아래 표는 계정 `852093844554`, 리전 `ap-northeast-2`의 최초 승인 계획입니다. 총예산은 180,000원이며 기존 리소스 변경이나 Inspector/CodeBuild 확장은 승인 범위 밖입니다.

최초 Terraform 결과는 **67 add / 0 change / 0 destroy**입니다. IAM 정책 연결 등도 별도 항목이므로 유료 서비스 67개라는 뜻은 아닙니다. 당시 로컬 state와 동명 프로젝트 자원의 부재를 확인했습니다. 현재 state에는 이번 신규 자원 47개가 있으므로 최초 저장 plan을 다시 적용하면 안 됩니다. 기존 기본 VPC는 대상에 포함하지 않습니다.

| 범위 | 생성 계획 |
|---|---|
| 네트워크 | 새 VPC 10.40.0.0/16, 서울 2a/2c subnet 2개, Internet Gateway, route table, flow log; 새 VPC의 default SG 제한 |
| EKS | `team4-eks` 1.35, 관리형 node group 1개, `t3.large` 기본 1대(min 1 / desired 1 / max 2), 노드당 암호화 gp3 20GiB와 public IPv4 |
| 기본 애드온 | VPC CNI `v1.22.4-eksbuild.3`, kube-proxy `v1.35.3-eksbuild.52`, CoreDNS `v1.13.2-eksbuild.51` |
| 이미지·시크릿 | ECR `team4-test`, KMS 키 1개와 alias, 테스트 Secret `team4/demo/token` |
| 복구 | ENI에 연결하지 않는 DemoOnly SG 1개, Config recorder/배달채널/restricted-ssh rule, EventBridge rule, Python Lambda 1개(기본 DRY_RUN) |
| 증적·오류 | S3 증적 버킷 1개, CloudWatch log group 3개, 실패 SQS queue 1개와 alarm 1개 |
| 인증 | IAM 역할 9개, 역할 정책·연결, EKS/GitHub OIDC provider 2개, EKS access entry 2개 |

EKS public API는 사용자가 제공한 관리 PC IPv4 **한 주소의 /32**로 제한합니다. 실제 주소는 Git에서 제외한 tfvars/plan에만 보관합니다. EKS 1.35의 STANDARD_SUPPORT와 2027-03-27 표준 지원 종료를 실제 AWS API로 확인했습니다. NAT Gateway, ALB, Inspector/CodeBuild 대응, SNS topic/subscription은 이번 계획에 없습니다. ENI 미연결 DemoOnly SG의 TCP22 임시 공개 및 자동복구 시험은 이번 승인에 포함됐습니다.

## 예상 비용과 유지 조건

[비용 산식과 출처](../COST_AND_CLEANUP.md)를 기준으로, **1노드 8시간 약 7,800원**, **2노드 8시간 약 9,300원**입니다. 24시간은 각각 약 16,800원/21,200원입니다. 공식 서울 가격표에서 확인한 EC2 $0.104/시간과 gp3 $0.0912/GB-month를 사용했습니다. 로그·Config·API 등의 임의 준비금(8시간 $3, 24시간 $5), 1 USD=1,500원 및 추가 10% 가정을 포함하며 확정 견적 또는 상한 보장이 아닙니다. 기존 계정 청구액과 장기 증적 보관료는 별도입니다. 1노드를 30일 유지하면 변동비를 제외한 소계만 약 254,000원이므로 180,000원 예산으로 상시 운영할 수 없습니다.

기본 1노드의 최대 8시간 실습 후 이번에 생성한 자원을 정리하는 데 승인받았습니다. 추가 노드로 확대하거나 장시간 유지하려면 범위·비용을 다시 확인합니다. 정리에 실패해 자원이 남으면 요금이 계속되므로 실제 잔존 자원을 확인합니다. 총 180,000원을 넘는 사용은 허가받은 것으로 간주하지 않습니다.

## 실행 전 남은 조건

- 사용자 승인 완료: 신규 생성·ECR/EKS 검증·DemoOnly SG 시험·검증 후 신규 자원 정리. 같은 범위에 대한 재승인을 요구하지 않습니다.
- [관리자 IAM bootstrap](TEAM4_IAM_PERMISSIONS.md): 초기 정책 6개와 신규 KMS 키를 확인하고 import했습니다. 신규 VPC DNS/기본 SG 및 클러스터 CNI/OIDC 권한은 반영 확인했습니다. 현재 실제 시작 템플릿의 노드 시작·S3 후속 조회 권한 보완이 남아 있습니다.
- bootstrap/import 뒤 state에 맞춰 계획을 다시 생성하고 승인된 자원·비용 범위를 대조합니다. 이 문서의 저장 plan을 그대로 강행하지 않습니다.
- GitHub `aws-demo` main 전용 환경과 격리된 일회용 runner 등록, OIDC 역할 생성은 완료했습니다. 검토한 main 코드·노드·보안 애드온이 준비되면 배포 workflow를 실행합니다.
- 실제 SG 복구 시연은 이미 승인된 범위에서 해당 새 DemoOnly SG가 ENI 미연결임을 재확인하고, 공개 TCP22 규칙을 일시 추가한 뒤 Config 탐지·Lambda 복구·재평가 증적을 확인합니다.

최초 VPC DNS 조회 거부는 실제 상태를 확인한 후 로컬 taint만 해제해 복구했고 네트워크·제어 영역 단계를 성공시켰습니다. 이후 54 add 계획을 원본과 대조해 실행했으며 현재 S3와 노드 권한 문제를 보완 중입니다. 수정 ZIP은 `generated/team4-node-s3-admin-20261023.zip`, 새 ID 장부는 `evidence/aws/full-partial-ledger-20261023.json`입니다. 키 생성 19:40:30 KST 기준 최대 8시간 창은 **10월 24일 03:40:30 KST**까지이며 신규 자원 정리는 미완료입니다.

## 원본 증적

- `evidence/aws/demo-plan.txt`: 실제 plan 명령 출력
- `evidence/aws/demo-plan.json`, `evidence/aws/demo.tfplan`: 기계 판독 및 저장 계획(Git 제외)
- `evidence/aws/preflight.json`, `names-before-plan.json`, `cluster-versions.json`, `instance-types.json`: 실제 읽기 조회

저장 plan SHA256: `788db65cb96fbc2304d14202c4c7ded0cd84e1ea545449ffc6a1758467c9bc1d`

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
