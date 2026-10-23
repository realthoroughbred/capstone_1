# 비용, 보존 및 정리 결정

2026-10-23 승인된 Terraform 자원 **67개를 생성**하고 EKS 1노드·ECR 서명 배포·보안 정책·ESO·Argo CD·실제 SG 자동복구 검증을 마쳤다. 실제 ID 장부는 `evidence/aws/full-created-ledger-20261023.json`이다. 최초 승인 plan **67 add / 0 change / 0 destroy**는 [검토 문서](docs/AWS_PLAN_REVIEW.md)에 보존했다. 검증 후 생성한 삭제 계획은 **0 add / 0 change / 67 destroy**이며 정확한 신규 ID를 대조했다. 최종 삭제 후 조회 결과는 `evidence/aws/cleanup-verification.json`과 [현재 상태](IMPLEMENTATION_STATUS.md)를 따른다. 누적 청구액은 아직 확인하지 않았다.

사용자는 **총예산 180,000원 내에서 위 계획의 신규 생성, 최대 8시간 실검증, ENI 미연결 DemoOnly SG의 TCP22 일시 공개·자동 복구, 검증 후 이번에 만든 자원 정리까지 승인**했다. 같은 범위의 정리 승인을 다시 요구하지 않는다. 기존·공유 자원은 보존하며 범위 확대나 장기 운영은 포함하지 않는다. KMS 생성 **10월 23일 19:40:30 KST**부터 계산한 8시간 창은 **10월 24일 03:40:30 KST**까지다. 실검증 종료 후 **10월 23일 22:58:06 KST**에 검토한 삭제 계획을 실행했다. 삭제 완료 시각은 실행 결과와 후속 AWS 조회로 확인한다.

## 단가와 실제 구성

서울 리전 EKS 1.35 standard support 1개, Linux `t3.large` On-Demand 노드 기본 1대, **노드당 gp3 20 GiB**가 실제 코드 값이다(`infra/main.tf`의 `volume_size=20`, 30 GiB가 아님). public IPv4는 노드당 1개로 계산한다. 프로젝트 CMK 1개와 Secret 1개가 있으며 EKS 로그 5종·VPC flow log를 365일 보관한다. NAT Gateway·ALB·EKS Auto Mode는 만들지 않는다. desired=1/max=2이고 autoscaler는 없으므로 아래 2대 표는 두 대가 계속 실행되는 경우의 비교다. node group 교체/업데이트 중 일시적인 추가 인스턴스 비용은 별도다.

| 항목 | 산정 입력과 확인 수준 |
| --- | --- |
| EKS control plane | 공식 **$0.10/cluster-hour**. standard support 조건이며 노드 비용 별도. [EKS 요금](https://aws.amazon.com/eks/pricing/) |
| Public IPv4 | 공식 **$0.005/IP-hour**. [VPC 요금](https://aws.amazon.com/vpc/pricing/) |
| `t3.large` Linux / Shared / On-Demand | 공식 서울 단가 **$0.104/node-hour**. SKU `822X28N5YHCZG5KZ`, `APN2-BoxUsage:t3.large`, USD/Hrs, `CapacityStatus=Used`, 추가 설치 소프트웨어 없음. [공식 지역 가격 CSV](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/20261015191316/ap-northeast-2/index.csv) |
| gp3 기본 성능, 노드당 20 GiB | 공식 서울 단가 **$0.0912/GiB-month**. SKU `MTK7D9SGKGYR3JD6`, `APN2-EBS:VolumeUsage.gp3`, USD/GB-Mo. 20 GiB는 한 달 $1.824이다. [공식 지역 가격 CSV](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/20261015191316/ap-northeast-2/index.csv) |
| 새 프로젝트 KMS CMK 1개 | 공식 **$1/key-month**, 시간 비례. 요청료 별도이며 장기 보유 후 키 회전은 추가 보관료가 생길 수 있다. [KMS 요금](https://aws.amazon.com/kms/pricing/) |
| Secrets Manager 1개 | 공개 요금 **$0.40/secret-month**, API **$0.05/10,000 calls**. ESO refresh 호출 포함. [Secrets Manager 요금](https://aws.amazon.com/secrets-manager/pricing/) |

EC2·gp3는 **AWS Price List의 공식 서울 지역 CSV 원문**에서 확인했다. 2026-10-23 최신 카탈로그 `20261022231453`의 같은 SKU·OnDemand·USD 행을 다시 조회했고 두 단가는 변하지 않았다. 선택 행은 `evidence/pricing/seoul-selected-prices-20261023.json`, 이전 조회는 `seoul-selected-prices.json`에 보존했다. 지역 인덱스에서 고정 버전 URL을 얻고 스트리밍으로 필요한 행을 읽었으며 전체 CSV는 저장하지 않았다. [최신 조회에 사용한 공식 가격표](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/20261022231453/ap-northeast-2/index.csv).

실제 실험은 EKS 제어 영역 1개와 `t3.large` 1노드, gp3 20 GiB 1개로 실행했다. 별도 로드밸런서·영구 볼륨은 없었다. 과거 부분 배포 장부를 최종 삭제 근거로 사용하지 않으며 KMS의 30일 삭제 대기와 Secret의 7일 복구 기간은 즉시 삭제와 구분한다.

gp3는 기본 3,000 IOPS·125 MB/s를 포함하며 이 구성은 추가 성능을 지정하지 않는다. 가격표의 GB는 1024³ bytes이므로 여기서는 GiB로 표기했다. [EBS 요금 및 단위](https://aws.amazon.com/ebs/pricing/). Free Tier·크레딧·약정 할인은 차감하지 않았다. 실제 사용량·청구 기간·가격 변경은 [AWS Pricing Calculator](https://calculator.aws/)와 생성 시점의 최신 요금으로 다시 대조한다.

## 8시간·24시간 예산 시나리오

월 요금은 비교를 위해 30일=720시간으로 나눈다. 실제 청구 월·초 단위 비례·최소 청구 단위에 따라 차이가 있다. **현재 승인 기간은 최대 8시간이며 24시간·30일 수치는 비용 비교용이다.** 노드 수 `N`, 유지 시간 `H`일 때 위 항목의 예비 소계는 다음과 같다.

```text
USD 소계 = H × [0.10 + N × (0.104 + 0.005 + 20 × 0.0912 / 720) + (1.00 + 0.40) / 720]
원화 예시 = USD × 1,500원/USD × 1.10
```

**환율 1,500원/USD와 VAT 10%는 예산 계산용 가정**이며 현재 은행환율이나 실제 계정의 확정 세금 고지가 아니다. 아래 변동비 준비금은 8시간 $3, 24시간 $5로 임의 배정한 실습 예비비다. 서비스 요금이나 예상 사용량의 검증 결과가 아니며 초과할 수 있다. **기존 계정의 누적 사용료는 조회·차감하지 않았다.**

| 지속 실행 조건 | 위 항목 소계 | 변동비 준비금 포함 | 원화 예시(백 원 올림) |
| --- | ---: | ---: | ---: |
| 노드 1대 / 8시간 | $1.71 | $4.71 | 약 7,800원 |
| 노드 1대 / 24시간 | $5.12 | $10.12 | 약 16,800원 |
| 노드 2대 / 8시간 | $2.60 | $5.60 | 약 9,300원 |
| 노드 2대 / 24시간 | $7.80 | $12.80 | 약 21,200원 |

달러는 소수 둘째 자리로 표시했으며 원화는 달러 반올림 전 계산값에 환율·VAT 가정을 적용한 뒤 백 원 단위로 올렸다. 고정 항목의 시간당 소계는 1대 약 $0.213478, 2대 약 $0.325011이다.

**노드 1대를 30일 상시 운영하면 변동비 없이도 예산을 넘는다.** 같은 입력의 720시간 소계는 EKS $72 + EC2 $74.88 + IPv4 $3.60 + EBS $1.824 + KMS/Secret $1.40 = **$153.704**다. 환율·VAT 가정 적용 시 약 **253,612원**으로 총예산 180,000원을 초과한다. 로그·요청·전송·기존 사용료는 여기에 추가된다.

이는 **생성부터 삭제까지 시간이 해당 시간일 때의 가정**이다. 8시간 사용 후 클러스터를 보존하면 요금이 계속 발생한다. 생성·설치·대기·실패 조사 시간도 포함해야 하며 이 표가 자동 종료나 예산 상한을 보장하지 않는다. 180,000원 중 예컨대 36,000원을 별도 안전 예비비로 남기고, `실습 가용액 = 180,000원 - 기존 사용액 - 안전 예비비 - 실험 뒤 보존비`로 산정한다. 실제 plan과 기존 사용액·유지 기간·변동비를 함께 검토하기 전에는 여러 날 상시 운영이 예산 안에 든다고 확정하지 않는다.

## 변동비에 포함해야 할 항목

| 항목 | 실제 사용량을 확인할 방법 / 계산에서 빠뜨리지 않을 조건 |
| --- | --- |
| CloudWatch | EKS api/audit/authenticator/controllerManager/scheduler와 VPC flow logs의 수집 GB, 압축 보관 GB-month, query scan GB, alarm 수를 기록한다. 365일 보존은 실험 후 비용도 남긴다. [CloudWatch 요금](https://aws.amazon.com/cloudwatch/pricing/) |
| Config / SG 복구 | 이번 승인 계획에 포함된다. configuration item 수와 rule evaluation 수를 센다. recorder는 SecurityGroup 종류를 기록하므로 기존 SG의 초기/변경 기록도 발생할 수 있다. [Config 요금](https://aws.amazon.com/config/pricing/) |
| S3 / ECR / KMS / Secrets API | 증적 버전까지 포함한 저장 GB-month, PUT/GET, 이미지·서명·SBOM 크기, 암복호화 및 ESO 요청 수를 계산한다. 저장 공간과 요청료는 별개다. [S3 요금](https://aws.amazon.com/s3/pricing/), [ECR 요금](https://aws.amazon.com/ecr/pricing/) |
| Lambda / EventBridge / SQS | 이번 SG 복구의 호출·실행 시간, 재시도, 실패 큐 요청을 포함한다. Inspector용 DynamoDB dedup/PITR는 이번 계획에 없다. |
| Inspector / 외부 CodeBuild | 이번 승인 계획에서는 비활성이다. 추후 추가한다면 enhanced 스캔 횟수·재스캔, build 실행 분, artifact/logs 및 외부 runner·인터넷/private 연결을 별도 견적한다. **위 표의 준비금으로 충당된다고 가정하지 않는다.** [Inspector 요금](https://aws.amazon.com/inspector/pricing/), [CodeBuild 요금](https://aws.amazon.com/codebuild/pricing/) |
| CPU credit / 데이터 전송 | T3 Unlimited의 추가 CPU credit은 공식 Linux **$0.05/vCPU-hour**다. 장시간 CPU 사용, AZ 간/인터넷 전송은 위 소계에 없다. [EC2 요금](https://aws.amazon.com/ec2/pricing/on-demand/) |

IAM·STS·EKS access entry/OIDC 인증 자체에 별도 유료 인프라를 추가하지 않으며, VPC CNI·CoreDNS·kube-proxy와 ESO/Kyverno/Argo CD는 같은 노드의 자원을 사용한다. controller 때문에 노드를 늘리거나 Marketplace addon, EKS Auto Mode 등을 추가하면 견적을 다시 만든다. 계정 기본 billing·Marketplace 선택 여부도 최종 plan과 대조한다.

EKS는 사용하지 않는 시간에도 클러스터 요금이 발생한다. 노드만 줄여도 control plane, 로그·이미지·secret·키 보관 비용은 남는다. 이번에는 최대 8시간 검증 후 승인된 신규 자원을 정리한다. AWS Budgets/비용 알림은 계정 관리자가 실제 수신자를 지정하여 구성하고 동작을 확인한다. 이 저장소가 예산 알림을 이미 구성했다고 주장하지 않는다.

## 배포 전후 자산 목록

[AWS_DEPLOYMENT_GUIDE](AWS_DEPLOYMENT_GUIDE.md)의 사전 조회로 기존 Config recorder, ECR registry scanning, GitHub OIDC provider, VPC/NAT/IP/Load Balancer를 먼저 구분한다. `Project=team4` 태그와 Terraform state를 함께 사용하되, 태그가 없거나 외부에서 만든 리소스도 확인한다.

배포 후에는 `terraform -chdir=infra state list` 및 `terraform -chdir=infra output`을 보관하고 EKS/node group/EC2/EBS/ENI/IPv4, ECR 이미지, Logs, KMS, Secrets Manager, 옵션별 S3/SQS/DynamoDB/Config/Lambda/EventBridge, 외부 CodeBuild/runner를 실제 AWS 조회와 대조한다. 이 문서에는 실제 생성 ID를 임의로 기입하지 않는다.

## 보존과 삭제 절차

상세 명령과 부분 실패 처리는 [승인된 신규 자원 정리 절차](docs/cleanup-notes.md)에 정리했다. 이미 승인된 정리를 실행하기 위한 확인 순서는 다음과 같다.

1. **신규 소유권을 고정한다.** 원본 승인 plan, 생성 전 조사, 실제 생성 응답과 state로 주소·ID·ARN ledger를 만든다. [로컬 검사 도구](scripts/check-cleanup-plan.py)는 기존 managed state, 미승인 주소, 다른 계정·리전·ID와 교체·수정이 섞인 destroy plan을 거부한다. binary plan을 직접 `terraform show -json`으로 읽어 제공 JSON과 대조하고 해시를 기록한다. 로컬 검사 PASS만으로 실제 소유권을 입증하지는 않는다.
2. **실험과 쓰기를 끝내고 보존한다.** 이번 EventBridge rule·Config recorder만 중지하고 실제 SG 복구 증거, 로그·실패 큐 조사 결과를 저장한다. S3의 모든 객체 버전과 삭제 마커, ECR의 모든 digest·하위 이미지·서명·SBOM을 내보내고 크기·해시·manifest를 확인한다. secret 값과 인증 token은 일반 증적에서 제외한다.
3. **백업된 정확한 신규 내용만 정리한다.** 신규 bucket의 Key+VersionId, 신규 repository의 digest를 명시해 삭제하고 다시 비었는지 조회한다. S3 `force_destroy=false`, ECR `force_delete=false`를 유지하며 보호 설정을 우회하지 않는다. controller가 만든 자원은 실제 소유권·종속성을 확인한다.
4. **검사한 저장 destroy plan으로 정리한다.** 부분 apply 실패도 현재 생성된 승인 범위만 정리한다. 삭제 실패 시 state·오류를 보존하고 새 plan으로 재검사한다. state에 빠진 자원은 정확한 생성 기록을 찾아 복구한 뒤 처리한다. 임의 `state rm`, lock 삭제, ENI 강제 detach로 문제를 숨기지 않는다.
5. **잔존 비용을 확인한다.** EC2/EBS/IP/ENI, EKS, S3/ECR/Logs와 자동화 자원을 실제 조회한다. Secrets Manager **7일 복구 기간**, KMS **30일 삭제 대기**는 유지하고 예약 ID·예정일을 별도 보고한다. 백업 검증은 KMS 삭제 예약 전에 끝낸다. 기존 VPC·공유 자원·외부 runner 및 관리자 IAM 정책은 이번 Terraform 정리 대상에서 제외한다. 청구 반영 지연도 후속 확인한다.

로그·증적의 365일 보존 설정은 destroy 뒤에도 자동으로 유지된다는 뜻이 아니다. 내보내기 실패로 일부 신규 저장 자원을 남겨야 한다면 정확한 ID·이유·예상 보관료를 보고하고 다른 확인된 신규 유료 자원을 우선 정리한다. `--approved-demo`는 SG 실험의 고유 TCP22 규칙 한 개와 실패 시 그 규칙의 복구를 제한하는 실행 옵션이며, 전체 신규 자원 정리의 근거는 사용자의 별도 명시적 승인이다. 이번 시험은 Lambda의 실제 제거를 확인했고 수동 시험 규칙 제거는 필요하지 않았다. 이어서 신규 자원 정리를 실행한 결과는 아래와 같다.

## 이번 실험의 정리 결과

Terraform 삭제는 **2026-10-23 23:09:10 KST**에 완료했고, **23:12:48 KST** 후속 AWS 조회 46개 항목이 통과했다. EKS·노드·EC2·EBS·ENI·신규 VPC 및 ECR/S3/Config/Lambda/EventBridge/SQS/프로젝트 역할의 정리를 확인했다. 기존 기본 VPC, 관리자 정책과 공유 서비스 연결 역할은 유지했다. Terraform managed state는 비어 있다.

KMS는 `PendingDeletion`, 삭제 예정 시각은 `2026-11-22T23:09:08.324000+09:00`다. Secret은 7일 복구 기간의 삭제 예약이며, CloudTrail의 성공한 DeleteSecret 응답에서 확인한 예정 시각은 `2026-10-30T13:58:19Z`다. DescribeSecret의 DeletedDate는 요청 시각으로 반환되어 예약 종료 시각의 근거로 사용하지 않았다. 두 항목은 물리적 삭제 완료로 표시하지 않는다. 원본 증거는 `evidence/aws/cleanup-verification.json`, 실행 로그는 `evidence/cleanup/destroy-final-apply-20261023.txt`다.

신규 KMS 생성부터 최종 재조회까지 약 **3.54시간**으로 8시간 창 안에 정리했다. 모든 기본 항목을 이 전체 시간에 적용한 보수적 산식은 $0.76이며, 기존 $3 변동비 예비액·환율 1,500원·VAT 10% 가정까지 넣으면 **약 6,200원**이다. 이 값은 청구액이나 확정 상한이 아니다. 실제 누적 사용료와 기존 계정 비용은 조회하지 않았으며 사용량·세금·청구 반영에 따라 달라진다.

보존한 자료: ECR digest 4개와 OCI blob 14개, S3 객체 버전 2개, Config SG 이력·평가, 배포 artifact, EKS/Lambda/VPC 로그 및 Terraform 계획·state·ID 장부. 로그 백업은 고정한 snapshot 종료 시각까지 조회된 내용이며 이후 늦게 도착한 로그와 정리 중 로그의 완전 보존은 주장하지 않는다. 원본 증거·state·tfvars·자격증명은 Git에서 제외한다.
