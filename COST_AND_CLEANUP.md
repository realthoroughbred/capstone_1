# 비용, 보존 및 정리 결정

현재 AWS apply 및 삭제를 실행하지 않았고 클라우드 리소스를 만들지 않았다. WSL `team4` profile의 IAM 사용자 `arn:aws:iam::852093844554:user/team4-operator`를 확인했고, 처음 AccessDenied였던 사전 조회 5개는 2026-10-18 09:45 UTC 재검증에서 모두 통과했다(`evidence/aws/preflight.json`). 사용자 제공 public IPv4 `/32`를 반영한 실제 plan은 **67 add / 0 change / 0 destroy**이며 [검토 문서](docs/AWS_PLAN_REVIEW.md)에 정리했다. 누적 청구액은 아직 확인하지 않았다. 생성 후에도 **사용자의 명시적 삭제 승인 전까지 리소스를 유지**한다. 자동 종료나 일괄 destroy를 예약하지 않았다.

사용자가 지정한 **총예산은 180,000원**이다. 이는 자동 사용 허가가 아니다. 실제 plan·예상 비용·유지 기간을 제시한 다음 과금 리소스 생성 승인을 별도로 받아야 한다. 승인 대상 자원과 실행 조건은 [생성 계획 검토](docs/AWS_PLAN_REVIEW.md)에 명시했다.

## 단가와 실제 구성

서울 리전 EKS 1.35 standard support 1개, Linux `t3.large` On-Demand 노드 기본 1대, **노드당 gp3 20 GiB**가 실제 코드 값이다(`infra/main.tf`의 `volume_size=20`, 30 GiB가 아님). public IPv4는 노드당 1개로 계산한다. 프로젝트 CMK 1개와 Secret 1개가 있으며 EKS 로그 5종·VPC flow log를 365일 보관한다. NAT Gateway·ALB·EKS Auto Mode는 만들지 않는다. desired=1/max=2이고 autoscaler는 없으므로 아래 2대 표는 두 대가 계속 실행되는 경우의 비교다. node group 교체/업데이트 중 일시적인 추가 인스턴스 비용은 별도다.

| 항목 | 산정 입력과 확인 수준 |
| --- | --- |
| EKS control plane | 공식 **$0.10/cluster-hour**. standard support 조건이며 노드 비용 별도. [EKS 요금](https://aws.amazon.com/eks/pricing/) |
| Public IPv4 | 공식 **$0.005/IP-hour**. [VPC 요금](https://aws.amazon.com/vpc/pricing/) |
| `t3.large` Linux / shared / On-Demand | **임시 예산 입력 $0.12/node-hour**. 서울의 정확한 현재 단가를 공식 지역 데이터로 확보하지 못했으므로 AWS 확정 단가가 아니다. 최종 계산기 견적으로 교체한다. [EC2 요금](https://aws.amazon.com/ec2/pricing/on-demand/) |
| gp3 기본 성능, 노드당 20 GiB | **임시 예산 입력 $0.12/GiB-month**. 서울 단가 미확정. 기본 3,000 IOPS·125 MB/s는 포함되며 추가 성능을 지정하지 않았다. [EBS 요금](https://aws.amazon.com/ebs/pricing/) |
| 새 프로젝트 KMS CMK 1개 | 공식 **$1/key-month**, 시간 비례. 요청료 별도이며 장기 보유 후 키 회전은 추가 보관료가 생길 수 있다. [KMS 요금](https://aws.amazon.com/kms/pricing/) |
| Secrets Manager 1개 | 공개 요금 **$0.40/secret-month**, API **$0.05/10,000 calls**. ESO refresh 호출 포함. [Secrets Manager 요금](https://aws.amazon.com/secrets-manager/pricing/) |

2026-10-18에 공식 요금 페이지를 확인했다. EC2/EBS의 소형 지역 JSON 후보 URL은 404였으며 대용량 전체 offer 파일은 내려받지 않았다. 따라서 위 **EC2·gp3 두 값은 계산을 재현하기 위한 가정**이며 실제보다 높다는 보장도 없다. Free Tier·크레딧·약정 할인은 차감하지 않았다. 최종 plan 뒤 [AWS Pricing Calculator](https://calculator.aws/)의 서울 리전 견적으로 바꾼다.

## 8시간·24시간 예산 시나리오

월 요금은 비교를 위해 30일=720시간으로 나눈다. 실제 청구 월·초 단위 비례·최소 청구 단위에 따라 차이가 있다. 노드 수 `N`, 유지 시간 `H`일 때 위 항목의 예비 소계는 다음과 같다.

```text
USD 소계 = H × [0.10 + N × (0.12 + 0.005 + 20 × 0.12 / 720) + (1.00 + 0.40) / 720]
원화 예시 = USD × 1,500원/USD × 1.10
```

**1,500원/USD와 추가 10%는 예산 계산용 가정**이며 현재 은행환율이나 확정 세금 고지가 아니다. 아래 변동비 준비금은 8시간 $3, 24시간 $5로 임의 배정한 실습 예비비다. 서비스 요금이나 예상 사용량의 검증 결과가 아니며 초과할 수 있다.

| 지속 실행 조건 | 위 항목 소계 | 변동비 준비금 포함 | 원화 예시(백 원 올림) |
| --- | ---: | ---: | ---: |
| 노드 1대 / 8시간 | $1.84 | $4.84 | 약 8,000원 |
| 노드 1대 / 24시간 | $5.53 | $10.53 | 약 17,400원 |
| 노드 2대 / 8시간 | $2.87 | $5.87 | 약 9,700원 |
| 노드 2대 / 24시간 | $8.61 | $13.61 | 약 22,500원 |

이는 **생성부터 삭제까지 시간이 해당 시간일 때의 가정**이다. 8시간 사용 후 클러스터를 보존하면 요금이 계속 발생한다. 생성·설치·대기·실패 조사 시간도 포함해야 하며 이 표가 자동 종료나 예산 상한을 보장하지 않는다. 180,000원 중 예컨대 36,000원을 별도 안전 예비비로 남기고, `실습 가용액 = 180,000원 - 기존 사용액 - 안전 예비비 - 실험 뒤 보존비`로 산정한다. 실제 plan 전에는 여러 날 상시 운영이 예산 안에 든다고 확정하지 않는다.

## 변동비에 포함해야 할 항목

| 항목 | 실제 사용량을 확인할 방법 / 계산에서 빠뜨리지 않을 조건 |
| --- | --- |
| CloudWatch | EKS api/audit/authenticator/controllerManager/scheduler와 VPC flow logs의 수집 GB, 압축 보관 GB-month, query scan GB, alarm 수를 기록한다. 365일 보존은 실험 후 비용도 남긴다. [CloudWatch 요금](https://aws.amazon.com/cloudwatch/pricing/) |
| Config / SG 복구 | 옵션이 켜졌을 때 configuration item 수와 rule evaluation 수를 센다. recorder는 SecurityGroup 종류를 기록하므로 기존 SG의 초기/변경 기록도 발생할 수 있다. [Config 요금](https://aws.amazon.com/config/pricing/) |
| S3 / ECR / KMS / Secrets API | 증적 버전까지 포함한 저장 GB-month, PUT/GET, 이미지·서명·SBOM 크기, 암복호화 및 ESO 요청 수를 계산한다. 저장 공간과 요청료는 별개다. [S3 요금](https://aws.amazon.com/s3/pricing/), [ECR 요금](https://aws.amazon.com/ecr/pricing/) |
| Lambda / EventBridge / SQS / DynamoDB | SG·Inspector 옵션의 호출·실행 시간, 재시도, 실패 큐 요청, dedup 읽기/쓰기·보관·PITR를 포함한다. 현재 기본값은 옵션 비활성이다. |
| Inspector / 외부 CodeBuild | enhanced 스캔 횟수·재스캔, build 실행 분, artifact/logs 및 외부 runner·인터넷/private 연결을 별도 견적한다. **위 표의 준비금으로 충당된다고 가정하지 않는다.** [Inspector 요금](https://aws.amazon.com/inspector/pricing/), [CodeBuild 요금](https://aws.amazon.com/codebuild/pricing/) |
| CPU credit / 데이터 전송 | T3 Unlimited의 추가 CPU credit은 공식 Linux **$0.05/vCPU-hour**다. 장시간 CPU 사용, AZ 간/인터넷 전송은 위 소계에 없다. [EC2 요금](https://aws.amazon.com/ec2/pricing/on-demand/) |

IAM·STS·EKS access entry/OIDC 인증 자체에 별도 유료 인프라를 추가하지 않으며, VPC CNI·CoreDNS·kube-proxy와 ESO/Kyverno/Argo CD는 같은 노드의 자원을 사용한다. controller 때문에 노드를 늘리거나 Marketplace addon, EKS Auto Mode 등을 추가하면 견적을 다시 만든다. 계정 기본 billing·Marketplace 선택 여부도 최종 plan과 대조한다.

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
