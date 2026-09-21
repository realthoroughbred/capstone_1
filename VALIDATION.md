# 검증 결과

## 완료한 검사

- 모든 셸 스크립트에 대해 bash -n 통과.
- 모든 Kubernetes·kind·Calico YAML 파싱 통과.
- 모든 Terraform .tf 파일의 HCL 파싱 통과.
- Terraform 1.12.2 fmt 실행 및 fmt -check 통과.
- Deployment selector와 Pod 라벨의 일치 확인.
- server Service와 컨테이너 포트 8080의 일치 확인.
- 임시 NetworkPolicy의 출발지·도착지 selector 확인.
- kind Pod CIDR과 Calico IP pool CIDR의 일치 확인.
- EKS 배포 파일 생성 시 세 Deployment 모두 ECR digest로 교체되는지 확인.

## 완료하지 못한 검사

- Terraform init은 AWS provider v6.65.0과 lock 파일을 생성했으나, 이후 validate에서 로컬 provider 캐시의 체크섬 불일치가 발생해 provider 스키마 검증을 완료하지 못했습니다. 이 작성 환경의 provider 캐시는 배포 파일에 포함하지 않았습니다.
- 사용자 PC의 Docker·WSL·kind·Calico 실행은 수행하지 않았습니다.
- AWS 자격증명을 사용한 plan/apply, EKS 생성, ECR 업로드, 통신 검증은 수행하지 않았습니다.
- 설치 스크립트에 지정된 모든 도구의 다운로드·설치를 실제로 실행한 것은 아닙니다.

## 사용 환경에서 확인할 순서

1. 각 로컬 단계의 정상 결과를 확인합니다.
2. AWS 리소스를 생성하기 전에 terraform init과 terraform validate를 실행합니다.
3. validate가 실패하면 apply하지 않고 해당 오류를 해결합니다.
4. plan을 검토한 뒤 지정한 담당자만 apply합니다.
5. EKS에서도 동일한 통신 시험으로 CNI 정책 집행을 검증합니다.

이 패키지는 재현을 위한 시작 구성과 설명서이며, 실제 환경에서 전 과정을 성공시킨 배포 인증 결과는 아닙니다.
