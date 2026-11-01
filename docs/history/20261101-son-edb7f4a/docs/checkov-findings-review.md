# Checkov 실패 항목 조치 및 예외 검토 보고서

- 환경: 로컬 Terraform 정적 분석
- Terraform 코드 변경 없음
- 실패 항목: 12건
- 예외 승인 상태: 전체 미승인

## 1. 검사 항목별 검토

| 검사 ID | 리소스 | 코드 위치 | 분류 | 검토 내용 |
|---|---|---|---|---|
| CKV_AWS_394 | aws_availability_zones.available | main.tf:1 | 설정 개선 검토 | 가용영역 식별자 고정 여부 검토 |
| CKV_AWS_130 | aws_subnet.public[0] | main.tf:14 | 예외 승인 검토 | 퍼블릭 IP 자동 할당 필요성과 접근 통제 확인 |
| CKV_AWS_338 | aws_cloudwatch_log_group.cluster | main.tf:46 | 설정 개선 검토 | 로그 보존기간 7일과 365일 기준 비교 |
| CKV_AWS_158 | aws_cloudwatch_log_group.cluster | main.tf:46 | 암호화 방식 검토 | CloudWatch KMS 키 적용 필요성 확인 |
| CKV_AWS_39 | aws_eks_cluster.demo | main.tf:50 | 예외 승인 검토 | EKS Public Endpoint 및 /32 CIDR 제한 검토 |
| CKV_AWS_58 | aws_eks_cluster.demo | main.tf:50 | AWS 기본 기능 검토 | EKS 1.35 기본 암호화와 고객 관리형 KMS 요구사항 확인 |
| CKV_AWS_37 | aws_eks_cluster.demo | main.tf:50 | 설정 개선 검토 | Control Plane 로그 5종 중 미설정 2종 검토 |
| CKV_AWS_136 | aws_ecr_repository.test | main.tf:171 | 암호화 방식 검토 | ECR AES256과 KMS 암호화 요구사항 비교 |
| CKV_AWS_130 | aws_subnet.public[1] | main.tf:14 | 예외 승인 검토 | 퍼블릭 IP 자동 할당 필요성과 접근 통제 확인 |
| CKV2_AWS_12 | aws_vpc.demo | main.tf:5 | 설정 개선 검토 | VPC 기본 보안 그룹의 트래픽 제한 검토 |
| CKV2_AWS_11 | aws_vpc.demo | main.tf:5 | 설정 개선 검토 | VPC Flow Logs 구성 검토 |
| CKV2_AWS_5 | aws_security_group.healing_demo | main.tf:182 | 예외 승인 검토 | 자동복구 실습용 미연결 보안 그룹 검토 |

## 2. 검토 원칙

- Checkov 실패는 자동으로 예외 승인하지 않는다.
- 실습 설계와 충돌하는 항목은 보완통제 및 승인 근거를 기록한다.
- 위험도 점수는 기존 ISMS-P 위험도 평가 보고서를 참조한다.
- Terraform 공용 인프라 코드는 팀 협의 후 변경한다.
- 실제 AWS EKS 적용 결과는 포함하지 않는다.

## 3. 후속 작업

- 팀원과 개선 대상 및 예외 후보 검토
- 보안 설정 개선 후 Checkov 재검사
- 승인된 예외만 근거와 범위를 기록
- GitHub Actions 재검증
