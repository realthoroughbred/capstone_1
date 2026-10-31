# ISMS-P 위험도 평가 자동화 보고서

- 생성일시: 2026-11-01 00:15:26 KST
- 분석 대상: Terraform IaC (infra/)
- 분석 도구: Checkov 3.3.29
- 평가 범위: 로컬 정적 분석 결과
- 평가 상태: 초기 위험도 산정 / 담당자 검토 필요

## 1. 검사 결과

- 통과: 37건
- 실패: 12건
- 실패 규칙 종류: 11종

## 2. 위험도 평가 기준

- 위험점수 = 발생 가능성(1~5) × 영향도(1~5)
- 상: 15~25점 / 중: 8~14점 / 하: 1~7점
- 점수는 프로젝트 내부 초기 평가값이며 공식 Checkov 심각도가 아님
- 실제 적용 환경과 보완통제 확인 후 최종 평가 필요

## 3. 위험등급별 현황

- 상: 4건
- 중: 6건
- 하: 2건
- 미평가: 0건

## 4. 취약점별 위험도 평가

| 검사 ID | 대상 리소스 | ISMS-P | 가능성 | 영향도 | 점수 | 등급 | 상태 |
|---|---|---|---:|---:|---:|---|---|
| CKV2_AWS_12 | aws_vpc.demo | 2.6.1 | 4 | 5 | 20 | 상 | 조치 검토 |
| CKV_AWS_37 | aws_eks_cluster.demo | 2.9.4 | 4 | 4 | 16 | 상 | 조치 검토 |
| CKV_AWS_39 | aws_eks_cluster.demo | 2.6.1 | 3 | 5 | 15 | 상 | 예외 검토 후보 |
| CKV_AWS_58 | aws_eks_cluster.demo | 2.7.2 | 3 | 5 | 15 | 상 | 조치 검토 |
| CKV2_AWS_11 | aws_vpc.demo | 2.10.2 | 3 | 4 | 12 | 중 | 조치 검토 |
| CKV_AWS_130 | aws_subnet.public[0] | 2.6.1 | 3 | 4 | 12 | 중 | 예외 검토 후보 |
| CKV_AWS_130 | aws_subnet.public[1] | 2.6.1 | 3 | 4 | 12 | 중 | 예외 검토 후보 |
| CKV_AWS_136 | aws_ecr_repository.test | 2.7.2 | 3 | 4 | 12 | 중 | 조치 검토 |
| CKV_AWS_158 | aws_cloudwatch_log_group.cluster | 2.7.2 | 3 | 4 | 12 | 중 | 조치 검토 |
| CKV_AWS_338 | aws_cloudwatch_log_group.cluster | 2.9.4 | 3 | 4 | 12 | 중 | 조치 검토 |
| CKV2_AWS_5 | aws_security_group.healing_demo | 2.8.1 | 2 | 2 | 4 | 하 | 조치 검토 |
| CKV_AWS_394 | aws_availability_zones.available | 2.8.1 | 2 | 2 | 4 | 하 | 조치 검토 |

## 5. 조치 권고 및 예외 검토

### 1. CKV2_AWS_12

- 검사 내용: Ensure the default security group of every VPC restricts all traffic
- 대상: aws_vpc.demo
- 초기 위험등급: 상
- 개선 방안: 기본 보안 그룹 트래픽 제한 검증
- 처리 상태: 조치 검토

### 2. CKV_AWS_37

- 검사 내용: Ensure Amazon EKS control plane logging is enabled for all log types
- 대상: aws_eks_cluster.demo
- 초기 위험등급: 상
- 개선 방안: EKS Control Plane 로그 활성화
- 처리 상태: 조치 검토

### 3. CKV_AWS_39

- 검사 내용: Ensure Amazon EKS public endpoint disabled
- 대상: aws_eks_cluster.demo
- 초기 위험등급: 상
- 개선 방안: EKS 엔드포인트 접근 범위 제한 검증
- 처리 상태: 예외 검토 후보

### 4. CKV_AWS_58

- 검사 내용: Ensure EKS Cluster has Secrets Encryption Enabled
- 대상: aws_eks_cluster.demo
- 초기 위험등급: 상
- 개선 방안: EKS Secrets 암호화 설정
- 처리 상태: 조치 검토

### 5. CKV2_AWS_11

- 검사 내용: Ensure VPC flow logging is enabled in all VPCs
- 대상: aws_vpc.demo
- 초기 위험등급: 중
- 개선 방안: VPC Flow Logs 활성화 검토
- 처리 상태: 조치 검토

### 6. CKV_AWS_130

- 검사 내용: Ensure VPC subnets do not assign public IP by default
- 대상: aws_subnet.public[0]
- 초기 위험등급: 중
- 개선 방안: 퍼블릭 IP 자동 할당 필요성 검토
- 처리 상태: 예외 검토 후보

### 7. CKV_AWS_130

- 검사 내용: Ensure VPC subnets do not assign public IP by default
- 대상: aws_subnet.public[1]
- 초기 위험등급: 중
- 개선 방안: 퍼블릭 IP 자동 할당 필요성 검토
- 처리 상태: 예외 검토 후보

### 8. CKV_AWS_136

- 검사 내용: Ensure that ECR repositories are encrypted using KMS
- 대상: aws_ecr_repository.test
- 초기 위험등급: 중
- 개선 방안: ECR KMS 암호화 적용 검토
- 처리 상태: 조치 검토

### 9. CKV_AWS_158

- 검사 내용: Ensure that CloudWatch Log Group is encrypted by KMS
- 대상: aws_cloudwatch_log_group.cluster
- 초기 위험등급: 중
- 개선 방안: CloudWatch KMS 암호화 적용
- 처리 상태: 조치 검토

### 10. CKV_AWS_338

- 검사 내용: Ensure CloudWatch log groups retains logs for at least 1 year
- 대상: aws_cloudwatch_log_group.cluster
- 초기 위험등급: 중
- 개선 방안: 로그 보존기간 365일 이상 검토
- 처리 상태: 조치 검토

### 11. CKV2_AWS_5

- 검사 내용: Ensure that Security Groups are attached to another resource
- 대상: aws_security_group.healing_demo
- 초기 위험등급: 하
- 개선 방안: 보안 그룹 연결 여부 확인
- 처리 상태: 조치 검토

### 12. CKV_AWS_394

- 검사 내용: Ensure aws_availability_zones data source pins zone identity so its result set does not silently expand when AWS adds an Availability Zone
- 대상: aws_availability_zones.available
- 초기 위험등급: 하
- 개선 방안: 가용영역 식별자 고정 검토
- 처리 상태: 조치 검토

## 6. 평가 한계 및 후속 작업

- 본 결과는 미배포 Terraform 코드의 정적 검사 결과임
- 예외 후보는 담당자 검토 및 승인 전까지 위반 항목으로 유지
- ISMS-P 매핑은 프로젝트 내부 기준이며 통제항목 적합성 검토 필요
- 실제 AWS/EKS 적용 후 보완통제 및 운영 증적 재검증 필요


## 7. Trivy 이미지 취약점 위험도 평가

- ISMS-P 매핑: 2.8.2 보안 테스트, 2.11.2 취약점 점검 및 조치
- 평가 기준: 프로젝트 내부 초기 위험도 기준

- CRITICAL: 0건
- HIGH: 0건
- 합계: 0건

검사한 이미지에서 HIGH/CRITICAL 취약점이 발견되지 않았습니다.
