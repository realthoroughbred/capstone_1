# 비용, 보존 및 정리 결정

현재 AWS plan/apply 및 삭제를 실행하지 않았고 클라우드 리소스를 만들지 않았다. WSL `team4` profile로 IAM 사용자 `arn:aws:iam::852093844554:user/team4-operator`의 STS 인증은 확인했지만 사전 조회 5개가 모두 AccessDenied였다(`evidence/aws/preflight.json`). 실제 기존 리소스 수·누적 청구액·잔여 리소스는 확인하지 못했다. 생성 후에도 **사용자의 새로운 명시적 삭제 승인 전까지 리소스를 유지**한다. 자동 종료나 일괄 destroy를 예약하지 않았다.

사용자가 지정한 **총예산은 180,000원**이다. 이는 자동 사용 허가가 아니다. 조회 권한을 해결하고 실제 plan·예상 비용·유지 기간을 제시한 다음 과금 리소스 생성 승인을 별도로 받아야 한다.

## 예상 비용

기본 설계는 서울 리전 EKS 1개, `t3.large` On-Demand 노드 1대, gp3 20 GiB, 노드 public IPv4, KMS, Secrets Manager, CloudWatch이다. NAT Gateway와 ALB는 만들지 않는다. `node_max_size=2`는 상한이며 기본 desired는 1이다. 추가 노드가 실행되면 비용도 늘어난다. EKS 버전은 standard support를 사용하도록 설정되어 있지만 실행 시점의 제공·지원 기간은 확인해야 한다.

| 항목 | 공식 단가 또는 산정 방법 |
| --- | --- |
| EKS standard support control plane | **$0.10/cluster-hour**, 24시간 기준 $2.40/일, 30일 기준 $72. 노드 비용 별도. [EKS 요금](https://aws.amazon.com/eks/pricing/) |
| AWS public IPv4 | **$0.005/IP-hour**, IP 1개를 24시간 쓰면 $0.12/일, 30일 $3.60. 실제 사용/유휴 IP 수를 계정에서 조사한다. [VPC 요금](https://aws.amazon.com/vpc/pricing/) |
| Secrets Manager | 기본 공개 요금 **$0.40/secret-month**, API **$0.05/10,000 calls**. 실제 리전·저장 기간·호출량을 확인한다. ESO refresh도 호출을 발생시킨다. [Secrets Manager 요금](https://aws.amazon.com/secrets-manager/pricing/) |
| EC2·EBS | 서울 `t3.large` Linux On-Demand 1대와 gp3 20 GiB의 최신 단가로 산정한다. 이 문서는 EC2의 정확한 시간당 단가를 검증했다고 주장하지 않는다. CPU credit 추가 과금 조건도 확인한다. [EC2 On-Demand 요금](https://aws.amazon.com/ec2/pricing/on-demand/), [EBS 요금](https://aws.amazon.com/ebs/pricing/) |
| KMS·ECR·Logs·전송 | CMK, API 요청, 이미지 저장/전송, VPC flow log와 EKS control-plane log의 수집·365일 보관량에 따라 변동한다. |
| 옵션: Config·Inspector·Lambda·S3·SQS·DynamoDB·CodeBuild | 기록/평가·스캔·실행·저장량에 따라 추가된다. CodeBuild와 그 인터넷/private 연결 비용은 외부 인프라까지 따로 산정한다. |

노드 1대와 소규모 실습 사용량을 가정한 **전체 데모 예산의 1차 범위는 약 $6–9/일(30일 $180–270)**이다. 이는 확정 견적이나 상한이 아니며 세금·환율, 사용량 증가, 대량 로그·스캔·전송, 외부 runner/CodeBuild 네트워크 비용은 제외한다. 최종 plan과 최신 서울 리전 단가로 [AWS Pricing Calculator](https://calculator.aws/) 견적을 만들어 생성 승인에 첨부한다. Free Tier나 크레딧으로 무료가 된다고 가정하지 않는다.

위 달러 예시는 180,000원 예산에 대한 승인된 원화 견적이 아니다. 실제 결제 환율·세금·이미 발생한 비용·증적 보존 비용과 예비비를 반영해 `가용액 = 180,000원 - 기존 사용액 - 예비비`, `검토 가능한 유지 기간 = 가용액 / 보수적으로 잡은 원화 일비용`으로 산정한다. 한 달 상시 운영이나 정해진 며칠이 예산 안에 든다고 아직 판단할 수 없다. 사용량·외부 연결비가 확정되기 전에는 선택 기능을 켜지 않는다.

EKS는 사용하지 않는 시간에도 클러스터 요금이 발생한다. 노드만 줄여도 control plane, 로그·이미지·secret·키 보관 비용은 남는다. 따라서 승인 시 유지 기간과 다시 검토할 날짜를 정한다. AWS Budgets/비용 알림은 계정 관리자가 실제 수신자를 지정하여 구성하고 동작을 확인한다. 이 저장소가 예산 알림을 이미 구성했다고 주장하지 않는다.

## 배포 전후 자산 목록

[AWS_DEPLOYMENT_GUIDE](AWS_DEPLOYMENT_GUIDE.md)의 사전 조회로 기존 Config recorder, ECR registry scanning, GitHub OIDC provider, VPC/NAT/IP/Load Balancer를 먼저 구분한다. `Project=team4` 태그와 Terraform state를 함께 사용하되, 태그가 없거나 외부에서 만든 리소스도 확인한다.

배포 후에는 `terraform -chdir=infra state list` 및 `terraform -chdir=infra output`을 보관하고 EKS/node group/EC2/EBS/ENI/IPv4, ECR 이미지, Logs, KMS, Secrets Manager, 옵션별 S3/SQS/DynamoDB/Config/Lambda/EventBridge, 외부 CodeBuild/runner를 실제 AWS 조회와 대조한다. 이 문서에는 실제 생성 ID를 임의로 기입하지 않는다.

## 보존과 삭제 절차

1. **삭제 제안을 먼저 구체화한다.** 대상 계정·리전·Terraform state·리소스 ID·공유 여부와 삭제 후 남을 비용을 목록으로 만든다. 필요한 증적·이미지·설정을 접근 통제된 위치에 내보내고 복구 가능성을 확인한다. secret 값이나 자격 증명은 증적에 넣지 않는다.
2. 리소스 생성 승인과 별도로 **새로운 삭제 승인**을 받는다. 이미 배포되었거나 실습이 끝났다는 이유만으로 삭제하지 않는다. 승인 전에는 리소스를 유지하고 누적 비용을 알린다.
3. 아래 destroy plan을 검토한다. 외부 controller가 만든 LoadBalancer/PVC/ENI가 있다면 소유자와 의존성을 먼저 확인한다. 이 기본 설계에 ALB가 없다는 사실만으로 계정에 ALB가 없다고 판단하지 않는다.

```bash
# 자격 증명·계정 확인 후, 삭제안 작성용. 아직 실행한 결과가 아니다.
export AWS_PROFILE=team4 AWS_REGION=ap-northeast-2 AWS_PAGER=""
aws sts get-caller-identity --profile team4 --region ap-northeast-2
terraform -chdir=infra state list
terraform -chdir=infra plan -destroy -out=reviewed-destroy.tfplan
terraform -chdir=infra show -no-color reviewed-destroy.tfplan
# 위 계획의 삭제 대상에 대한 새로운 명시적 승인 후에만:
terraform -chdir=infra apply reviewed-destroy.tfplan
```

4. 보호 설정으로 삭제가 막히면 원인을 검토한다. ECR `force_delete=false`, 증적 S3 `force_destroy=false`이므로 이미지나 버전 객체를 임의로 비우거나 보호를 우회하지 않는다. Secrets Manager는 7일 복구 기간, KMS는 30일 삭제 대기 기간을 설정한다. 로그·증적의 365일 보존 설정은 destroy 시 반드시 유지된다는 뜻이 아니므로 먼저 내보낸다. DynamoDB dedup 기록도 삭제하면 재실행 방지가 사라진다.
5. apply 종료 뒤 계정 조회를 반복하여 남은 EC2/EBS/IP/ENI/NAT/LoadBalancer, ECR/S3 버전 객체, Logs/secret/키, Config recorder, CodeBuild/runner를 재확인한다. 외부 CodeBuild·공유 recorder·공유 OIDC provider는 이 프로젝트 소유인지 별도 판단하고 승인 범위 밖이면 유지한다. 청구 반영 지연을 고려하여 비용 화면도 후속 확인한다.

SG 데모 CLI의 `--approved-demo`는 **이번 실험에서 만든 고유 TCP22 규칙 1개와 실패 시 그 규칙의 정리**를 승인하는 옵션이다. 전체 AWS 리소스 삭제 승인과는 다르다. 정리 실패가 `MANUAL_REVIEW_REQUIRED`로 기록되면 실제 SG의 태그·ENI·규칙 ID를 확인하고 운영자가 조치해야 한다. 현재 그러한 실험이나 정리도 실행하지 않았다.
