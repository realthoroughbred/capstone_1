# 4조 공통 개발 환경과 EKS 테스트 환경 구축 설명서

이 설명서는 공통 개발 환경 준비와 테스트용 컨테이너 및 AWS 환경 구성을 다룹니다. Windows x86_64 컴퓨터에서 WSL2 Ubuntu와 Docker Desktop을 사용하는 기준입니다. macOS, ARM Windows, 학교 공용 서버는 설치 명령을 그대로 적용하지 않습니다.

목표는 로컬 Kubernetes와 AWS EKS에서 동일한 테스트 이미지로 server, client, unauthorized Deployment를 실행하고 통신을 확인하는 것입니다. server는 연결 검증용 한 줄 응답만 제공합니다. 별도 웹서비스 개발은 필요하지 않습니다.

검사·SBOM·ESO·Kyverno·Config·Lambda·대시보드는 이후 작업입니다. 여기에는 그 기능들을 붙일 기반 환경과 CNI 작동 확인용 임시 정책만 들어 있습니다.

## 0 작업 주체와 실행 위치

| 단계 | 누가 실행 | 실행 위치 |
|---|---|---|
| WSL2 설치 | 각 팀원 | Windows 관리자 PowerShell |
| Docker Desktop 설치와 WSL 연결 | 각 팀원 | Windows |
| CLI 설치와 로컬 Kubernetes | 각 팀원 | Ubuntu 터미널 |
| GitHub 저장소 생성 | 저장소 담당자 1명 | GitHub 웹 |
| GitHub 복제와 개인 브랜치 | 각 팀원 | Ubuntu 터미널 |
| Terraform AWS 생성·변경·삭제 | 지정한 인프라 담당자 1명 | 담당자의 Ubuntu 터미널 |
| 공용 EKS 접속 | 권한을 받은 각 팀원 | 각자의 Ubuntu 터미널 |

각자 만드는 kind 클러스터는 서로 다른 로컬 환경입니다. 같은 YAML로 재현할 수 있다는 의미이며 서로의 로컬 Pod에 접속하는 구조가 아닙니다. EKS는 팀 공용 하나만 만듭니다.

초기 Terraform은 지정 담당자의 로컬 state로 관리합니다. 나머지 팀원이 같은 코드를 별도로 apply하면 중복 생성이나 이름 충돌이 생깁니다. 여러 사람이 Terraform을 실행해야 할 때는 먼저 잠금 기능이 있는 S3 원격 state로 전환합니다. state를 Git에 올리거나 임의로 삭제하지 않습니다.

단계가 실패하면 다음 단계로 넘어가지 말고 마지막 명령과 오류를 확인합니다. 설치 스크립트는 오류가 나면 멈추도록 작성되어 있습니다.

## 1 Windows에 WSL2 Ubuntu 준비

시작 메뉴에서 PowerShell을 찾아 관리자 권한으로 실행합니다.

```powershell
wsl --status
wsl --list --verbose
```

Ubuntu가 이미 있고 VERSION이 2이면 재설치하지 않습니다. 없다면 다음 명령을 실행하고 필요하면 Windows를 재부팅합니다.

```powershell
wsl --install -d Ubuntu-24.04
```

시작 메뉴에서 Ubuntu를 열고 Linux 사용자 이름과 비밀번호를 만듭니다. sudo 비밀번호를 입력할 때 화면에 글자가 나타나지 않는 것은 정상입니다.

다시 PowerShell에서 확인합니다.

```powershell
wsl --update
wsl --list --verbose
```

설치된 배포판이 VERSION 1이면 목록에 표시된 정확한 이름으로 변환합니다.

```powershell
wsl --set-version Ubuntu-24.04 2
```

정상 기준은 Ubuntu 배포판의 VERSION 2입니다. 배포판 이름이 Ubuntu라면 위 명령의 이름도 Ubuntu로 바꿉니다.

공식 절차: https://learn.microsoft.com/en-us/windows/wsl/install

## 2 Docker Desktop과 Ubuntu 연결

Windows용 Docker Desktop을 공식 사이트에서 설치하고 실행합니다.

1. Settings → General에서 WSL 2 기반 엔진 사용을 확인합니다.
2. Settings → Resources → WSL Integration에서 사용할 Ubuntu를 활성화합니다.
3. Apply/Restart를 실행합니다.
4. Docker Desktop의 Kubernetes 기능은 이 가이드에서 사용하지 않습니다. Kubernetes는 kind가 만듭니다.
5. Ubuntu 터미널을 새로 열어 다음 명령을 실행합니다.

```bash
uname -m
docker version
docker run --rm hello-world
```

`uname -m`은 x86_64, `docker version`은 Client와 Server 정보, 마지막 명령은 Hello from Docker 메시지가 나와야 합니다. Docker Desktop 방식과 별도의 Ubuntu Docker Engine 설치를 동시에 섞지 않습니다.

로컬 리소스 계획의 시작값은 WSL에 CPU 4개와 메모리 약 6GB를 사용할 수 있는 환경입니다. 이는 보장되는 최소 사양이 아니며 다른 프로그램 사용량에 따라 달라집니다. 메모리가 부족하면 AWS 단계에 앞서 로컬 노드 수와 실행 중 프로그램을 조절합니다.

공식 연결 설명: https://docs.docker.com/desktop/features/wsl/

## 3 파일 준비와 GitHub 저장소 생성

이 압축파일을 내려받아 풉니다. 내부의 `team4-startup` 폴더에는 README.md, config, containers, infra, k8s, policies, scripts와 숨김 Git 설정 파일이 있습니다.

Windows 다운로드 폴더에 압축파일이 있다면 Ubuntu에서 다음과 같이 복사하고 해제할 수 있습니다. WIN_USER는 Windows 사용자 폴더 이름으로 바꿉니다. 아래 예시는 ZIP이 다운로드 폴더에 있다는 가정입니다.

```bash
sudo apt-get update
sudo apt-get install -y git unzip
mkdir -p ~/projects
cd ~/projects
unzip /mnt/c/Users/WIN_USER/Downloads/team4-startup-guide.zip
cd ~/projects/team4-startup
```

가능하면 작업 폴더는 `/mnt/c`보다 Ubuntu의 `~/projects` 안에 둡니다. 파일을 Windows 탐색기로 보고 싶으면 해당 폴더에서 `explorer.exe .`를 실행합니다.

이미 팀 저장소가 있다면 새 저장소를 만들지 않고 기존 저장소를 복제합니다. 기존 파일과 충돌하는지 확인하면서 이 예제 파일을 추가합니다. 새 프로젝트라면 저장소 담당자만 GitHub에서 빈 저장소를 만듭니다.

1. New repository → 이름 `team4-cloud-security` 입력.
2. 초기에는 Private 선택.
3. README, .gitignore, License 자동 생성은 선택하지 않음. 이 폴더의 파일로 최초 커밋할 예정입니다.
4. Settings → Collaborators 또는 Collaborators and teams에서 팀원 초대.
5. 팀원은 각자 초대를 수락.

### Git 인증

각자 Ubuntu에서 개인 SSH 키를 생성합니다. 기존 키가 있으면 덮어쓰지 말고 기존 등록 상태부터 확인합니다.

```bash
ssh-keygen -t ed25519 -C "YOUR_GITHUB_EMAIL"
```

기본 저장 경로를 사용하고 암호를 설정합니다. 그 후 공개키를 확인합니다.

```bash
cat ~/.ssh/id_ed25519.pub
```

이 `.pub` 내용만 GitHub → Settings → SSH and GPG keys → New SSH key에 등록합니다. 비공개 키인 id_ed25519는 공유하지 않습니다.

```bash
ssh -T git@github.com
```

처음 연결 시 표시되는 서버 지문은 GitHub 공식 SSH 지문과 대조합니다. `successfully authenticated`가 나오면 인증 성공입니다. GitHub는 SSH 셸을 제공하지 않으므로 이 명령이 종료 코드 1을 반환할 수 있습니다.

공식 절차: https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent

### 저장소 담당자 최초 업로드

다음 YOUR_NAME, YOUR_EMAIL, OWNER는 실제 값으로 바꿉니다.

```bash
cd ~/projects/team4-startup
git init -b main
git config user.name "YOUR_NAME"
git config user.email "YOUR_EMAIL"
git add .
git status
git commit -m "Add local and EKS bootstrap environment"
git remote add origin git@github.com:OWNER/team4-cloud-security.git
git push -u origin main
```

`git status`에 비밀정보, terraform.tfvars, tfstate, .terraform, AWS 설정 파일이 들어 있지 않아야 합니다. .gitignore가 준비되어 있습니다. Terraform이 생성하는 `.terraform.lock.hcl`은 버전을 고정하는 파일이므로 커밋합니다.

### 다른 팀원

```bash
cd ~/projects
git clone git@github.com:OWNER/team4-cloud-security.git team4-startup
cd team4-startup
git config user.name "YOUR_NAME"
git config user.email "YOUR_EMAIL"
git switch -c feature/jimin-environment
```

브랜치는 본인 이름과 작업명으로 구분합니다. main 보호 설정이 가능한 저장소에서는 직접 push 대신 PR 검토를 사용합니다.

## 4 CLI 도구 설치

이후 모든 명령은 특별한 표시가 없으면 Ubuntu 터미널에서 실행합니다.

```bash
cd ~/projects/team4-startup
cat config/versions.env
less scripts/01-install-tools.sh
bash scripts/01-install-tools.sh
```

less는 q로 종료합니다. 스크립트는 kubectl, kind, Helm, Terraform, AWS CLI v2를 설치합니다. Docker Desktop은 앞 단계에서 따로 설치합니다. kubectl, Helm, Terraform 다운로드는 제공 체크섬으로 검사합니다. 다운로드 자체가 실패하면 실행하지 않고 중단됩니다.

이 가이드는 참조 버전 조합을 파일에 고정했습니다. 최신 버전이라는 의미는 아닙니다. AWS CLI는 설치 시점 v2 배포판이므로 최초 담당자가 설치 버전을 기록하고 팀원이 맞춥니다. EKS의 Kubernetes 버전은 1.35를 제안하며 실제 계정·리전에서 지원하는지 AWS 단계에서 다시 확인합니다. kind 노드 이미지는 kindest/node:v1.35.0입니다.

각 명령을 확인합니다.

```bash
git --version
docker version
aws --version
kubectl version --client
helm version --short
terraform version
kind version
```

역할은 다음과 같습니다.

| 명령 | 역할 |
|---|---|
| docker | 이미지 빌드와 로컬 컨테이너 실행 |
| kind | Docker 안에 로컬 Kubernetes 생성 |
| kubectl | Kubernetes에 YAML 적용·상태 조회 |
| helm | 이후 ESO, Kyverno 같은 프로그램 설치 |
| terraform | AWS 리소스를 코드로 생성·변경 |
| aws | AWS 로그인·정보 조회·ECR 인증 |

설치 출처: https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/ · https://kind.sigs.k8s.io/docs/user/quick-start/ · https://helm.sh/docs/intro/install/ · https://developer.hashicorp.com/terraform/install · https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

## 5 로컬 Kubernetes와 Calico 생성

먼저 설정 파일을 확인합니다.

```bash
cat config/kind.yaml
cat config/calico-installation.yaml
```

kind 설정은 control-plane 1개와 worker 1개입니다. disableDefaultCNI를 true로 두고 Calico를 설치합니다. Pod CIDR은 10.244.0.0/16으로 두 파일에서 동일하게 사용합니다. 집·학교·VPN 네트워크와 겹치면 생성 전에 두 파일의 CIDR을 함께 수정합니다.

```bash
bash scripts/02-local-cluster.sh
```

스크립트의 실제 작업은 다음과 같습니다.

1. Docker 엔진 연결 확인.
2. `kind create cluster --name team4 --image kindest/node:v1.35.0 --config config/kind.yaml` 실행.
3. Calico의 CRD와 operator 설치.
4. Installation 리소스로 VXLAN 네트워크 구성.
5. 노드 Ready와 CoreDNS Deployment 준비 상태 확인.

CNI를 설치하기 전 노드가 NotReady인 것은 예상되는 중간 상태입니다. 따라서 CNI 설치 전의 kind create 단계에 모든 노드 Ready를 기다리는 옵션을 추가하면 안 됩니다.

```bash
kubectl --context kind-team4 get nodes
kubectl --context kind-team4 get pods -A
kubectl --context kind-team4 get tigerastatus
```

정상 기준은 `team4-control-plane`과 `team4-worker` 모두 Ready이며 Calico와 CoreDNS Pod가 준비 상태인 것입니다. Calico operator 상태가 일시적으로 갱신 중일 수 있으므로 관련 Pod와 이벤트를 함께 봅니다.

기존 이름의 클러스터가 다른 설정으로 만들어졌다면 스크립트가 설정을 자동 변환하지 않습니다. 그 로컬 클러스터에 필요한 작업이 없는지 확인한 뒤 `kind delete cluster --name team4`로 삭제하고 재생성합니다.

공식 구성: https://docs.tigera.io/calico/latest/getting-started/kubernetes/kind

## 6 테스트 이미지 빌드와 로컬 Pod 실행

테스트 이미지의 Dockerfile은 다음 구조입니다.

```dockerfile
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
WORKDIR /srv
COPY index.html /srv/index.html
USER 10001:10001
EXPOSE 8080
CMD ["busybox", "httpd", "-f", "-p", "8080", "-h", "/srv"]
```

기존 BusyBox 이미지에 연결 확인용 파일 한 개만 넣습니다. server는 8080 포트에서 `team4 server ok`를 돌려주고, client와 unauthorized는 같은 이미지 안의 wget으로 요청합니다. 이 Dockerfile이 이후 이미지 빌드·SBOM·서명 작업의 입력이 됩니다.

```bash
bash scripts/03-local-workloads.sh
```

실제 작업은 다음과 같습니다.

1. BusyBox 1.37.0을 조회하고 원본 digest 기록.
2. 해당 digest를 BASE_IMAGE로 지정해 team4-test:v1 빌드.
3. kind 노드의 이미지 저장소로 이미지 로드.
4. demo namespace 생성.
5. server, client, unauthorized Deployment와 server Service 생성.
6. Pod 준비 상태 확인 후 두 client에서 접속.

Docker 엔진에서 빌드한 이미지가 kind 노드에 자동으로 존재하는 것은 아닙니다. `kind load docker-image`가 그 이미지를 로컬 Kubernetes 노드에 전달합니다.

```bash
kubectl --context kind-team4 -n demo get deployments,pods,services
kubectl --context kind-team4 -n demo exec deployment/client -- wget -T 5 -qO- http://server:8080
kubectl --context kind-team4 -n demo exec deployment/unauthorized -- wget -T 5 -qO- http://server:8080
```

이 단계에서는 두 요청 모두 `team4 server ok`를 반환해야 정상입니다. unauthorized라는 이름만으로 차단되는 것이 아닙니다. 아직 정책을 적용하지 않았기 때문입니다.

Deployment는 Pod를 유지하는 설정, Service는 바뀌는 Pod IP 대신 일정한 이름과 내부 IP로 접속하게 하는 설정입니다. 외부 LoadBalancer는 생성하지 않습니다.

## 7 CNI가 실제로 정책을 적용하는지 확인

이 단계는 최종 NetworkPolicy 전체 구현이 아니라 설치한 CNI의 동작 검사입니다.

```bash
bash scripts/04-cni-smoke-test.sh kind-team4
```

스크립트는 다음 순서로 확인합니다.

1. 정책 적용 전 양쪽 접속 성공 확인.
2. server에 client만 접속하도록 임시 Ingress 정책 적용.
3. DNS 영향을 피하기 위해 동일한 Service IP로 재요청.
4. client 성공, unauthorized 실패 확인.
5. 임시 정책 삭제.
6. unauthorized 접속 복구 확인.

정상 종료 시 `PASS: baseline allowed, policy blocked only unauthorized, removal restored connection.`이 표시됩니다. 실패 시 단순히 정책이 존재한다고 성공으로 처리하지 않습니다.

최종 프로젝트에서 사용할 기본 입·출력 차단, DNS 허용, 세부 경로 정책은 이 테스트 이후 별도 작업으로 작성합니다.

## 8 팀 공통 값 기록

| 항목 | 이 예제 값 |
|---|---|
| 로컬 cluster/context | team4 / kind-team4 |
| AWS cluster/context alias | team4-eks / team4-eks |
| namespace | demo |
| 라벨 | app=server, app=client, app=unauthorized |
| 테스트 포트 | TCP 8080 |
| AWS 리전 | ap-northeast-2 |
| 이미지 repository | team4-test |
| 로컬 이미지 | team4-test:v1 |
| AWS 이미지 | ECR repository@sha256:… |

다음 명령은 실습 계정 설정이나 비밀값 없이 설치 버전만 기록합니다.

```bash
mkdir -p evidence
git --version > evidence/git-version.txt
docker version > evidence/docker-version.txt
aws --version > evidence/aws-version.txt 2>&1
kubectl version --client > evidence/kubectl-version.txt
kind version > evidence/kind-version.txt
helm version --short > evidence/helm-version.txt
terraform version > evidence/terraform-version.txt
```

검토 후 공통 버전 목록은 docs에 옮겨 커밋할 수 있습니다. evidence는 작업 결과 기본 보관 위치이며 Git에서는 제외됩니다.

여기까지가 각 팀원의 로컬 환경 완료 지점입니다.

## 9 AWS 단계의 구성과 비용 발생 지점

아래는 팀 인프라 담당자 한 명이 진행합니다. 로컬 작업은 AWS 없이 가능하지만 `terraform apply`부터 실제 AWS 리소스와 비용이 발생합니다.

이 예제의 AWS 구성은 다음과 같습니다.

| 리소스 | 구성 |
|---|---|
| VPC | 10.40.0.0/16, DNS 활성화 |
| 서브넷 | 서로 다른 AZ의 public subnet 2개 |
| 외부 경로 | Internet Gateway와 route table |
| EKS | 관리 API의 private endpoint 활성화, public endpoint는 팀원 공인 IPv4 /32만 허용 |
| 워커노드 | AL2023 Linux t3.medium 1개, 최대 2개 |
| 노드 디스크 | 암호화된 gp3 20GB |
| 노드 접근 | SSH key·remote access 미설정, 인터넷 인바운드 허용 규칙 없음 |
| ECR | 태그 덮어쓰기 제한, 업로드 시 스캔 |
| EKS add-on | VPC CNI, kube-proxy, CoreDNS |
| 로그 | API·audit·authenticator, 보존 7일 |
| 복구 시연 SG | 아무 장비에도 연결하지 않은 별도 SG, DemoOnly=true |

NAT Gateway와 ALB를 만들지 않아 초기 비용을 줄이는 실습 구성입니다. 대신 노드가 public subnet에서 공인 IP를 사용합니다. 공인 IP가 있다고 포트가 자동 공개되는 것은 아니며 인바운드는 보안 그룹으로 제어합니다. 운영 환경으로 확장할 때는 private node와 NAT 또는 필요한 VPC endpoint를 설계합니다.

이 기본 환경을 Checkov 전체 규칙에 넣었을 때 무조건 통과한다고 보장하지 않습니다. 공개 서브넷 등 실습 선택과 최종 보안 요구사항은 검사 담당자가 구분해서 평가해야 합니다.

과금은 EKS control plane, EC2, EBS, 공인 IPv4, ECR, CloudWatch 등에 발생합니다. AWS Budgets 알림을 설정하되 예산 알림 자체가 리소스를 자동 정지시키지는 않습니다. 작업 종료 때 EC2만 중지해도 EKS 요금은 남을 수 있습니다.

공식 설명: https://aws.amazon.com/eks/pricing/ · https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html

## 10 AWS 계정 권한과 CLI 로그인

팀 AWS 계정 관리자가 먼저 개인별 로그인 권한을 준비합니다. 루트 계정이나 공용 액세스 키를 팀원에게 공유하지 않습니다.

권한은 두 종류입니다.

- Terraform 담당자의 AWS 리소스 생성 권한: EKS, EC2/VPC, ECR, IAM role과 policy attachment, iam:PassRole, EKS access entry, CloudWatch Logs 등에 대한 프로젝트 범위 권한. 최초 서비스 사용 시 필요한 service-linked role 생성도 허용되어야 합니다.
- 팀원의 Kubernetes 접근 권한: EKS access entry와 연결된 policy. GitHub 권한이나 AWS 콘솔 로그인만으로 자동 부여되지 않습니다.

학교·기관이 제공한 계정에서 IAM 생성이 제한되면 관리자가 역할을 미리 만들어 주거나 허용 범위를 조정해야 합니다. 권한 오류가 발생할 때 자격증명을 코드에 넣어 우회하지 않습니다.

IAM Identity Center가 준비되어 있다면 각자 다음 명령을 실행합니다.

```bash
aws configure sso --profile team4
```

입력할 값은 계정 관리자가 제공한 SSO Start URL 또는 Issuer URL, SSO 리전, 배정된 AWS 계정·역할입니다. SSO 리전과 EKS 리전은 서로 다를 수 있습니다. 기본 작업 리전은 ap-northeast-2, 출력은 json으로 선택합니다.

```bash
aws sso login --profile team4
export AWS_PROFILE=team4
export AWS_REGION=ap-northeast-2
aws sts get-caller-identity
```

SSO를 사용하지 않는 실습 계정이면 관리자가 제공한 개인별 임시 자격증명 방식에 맞춰 named profile을 구성합니다. `aws configure sso`가 모든 계정에 자동으로 SSO를 만들어 주는 것은 아닙니다.

정상 기준은 예상한 Account와 개인 IAM 신원입니다. `Unable to locate credentials`면 로그인이나 AWS_PROFILE을 먼저 확인합니다. 새 터미널에서는 AWS_PROFILE을 다시 지정해야 합니다.

공식 설명: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html

## 11 Terraform 입력값 작성

```bash
cd ~/projects/team4-startup
cp infra/terraform.tfvars.example infra/terraform.tfvars
nano infra/terraform.tfvars
```

nano에서는 Ctrl+O, Enter로 저장하고 Ctrl+X로 종료합니다.

수정할 항목은 다음과 같습니다.

1. aws_account_id: 실제 12자리 계정 번호.
2. admin_public_cidrs: 팀원별 인터넷 출구 IPv4에 /32를 붙인 값.
3. operator_principal_arns: 인프라 담당자를 포함해 접속할 팀원의 영구 IAM user 또는 role ARN.
4. 프로젝트 이름과 리전을 바꿨다면 config/versions.env도 함께 일치시킴.

공인 IP는 다음 읽기 명령으로 확인할 수 있습니다.

```bash
curl -4fsS https://checkip.amazonaws.com
```

`192.168.x.x`, `10.x.x.x` 같은 PC의 사설 IP를 넣지 않습니다. 예시 `203.0.113.10`은 실제 접속 가능한 주소가 아니므로 반드시 교체합니다. 집·학교 이동, VPN 전환, 공유기 재접속으로 공인 IP가 바뀌면 인프라 담당자가 allowlist를 갱신합니다.

IAM role ARN은 AWS 콘솔 IAM → Roles → 실제 로그인 역할 → ARN에서 확인합니다. SSO 역할에는 aws-reserved 경로가 포함될 수 있으므로 복사한 값을 그대로 씁니다. `aws sts get-caller-identity`에 나오는 `arn:aws:sts::…:assumed-role/…/세션`을 입력하면 안 됩니다.

예제는 등록한 operator에게 초기 전용 클러스터 관리 권한을 부여합니다. 작업 분담이 안정되면 namespace 단위 편집·조회 등으로 줄입니다. 이 권한은 AWS 계정 전체 Administrator 권한과 별개입니다.

## 12 EKS와 add-on 버전 확인

```bash
aws eks describe-cluster-versions --region ap-northeast-2 --output table
```

실제 리전에서 Kubernetes 1.35 생성과 표준 지원 상태를 확인합니다. 오래된 AWS CLI에서 명령이 없다면 CLI v2를 갱신하거나 EKS 콘솔에서 확인합니다.

```bash
bash scripts/05-addon-versions.sh
```

이 스크립트는 AWS API에서 Kubernetes 1.35와 호환되는 기본 add-on 버전을 조회하고 `infra/addons.auto.tfvars.json`에 정확한 버전을 고정합니다. VPC CNI가 이 설명서의 전제인 1.21 이상인지 확인합니다. 해당 버전이 제공되지 않으면 임의로 진행하지 말고 리전·Kubernetes·CNI 호환 조합을 다시 선택합니다.

이 스크립트는 매번 apply 전에 실행하는 용도가 아닙니다. 최초 선택 후 버전을 유지하고, 의도적인 업데이트 때 다시 조회합니다. AWS 추천 add-on 값은 로컬 .terraform.lock.hcl과 별도로 관리됩니다.

공식 호환 범위: https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html · https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html

## 13 Terraform 초기화와 검토

```bash
terraform -chdir=infra init
terraform -chdir=infra fmt
terraform -chdir=infra validate
terraform -chdir=infra plan -out=team4.tfplan
```

| 명령 | 의미 |
|---|---|
| init | AWS provider와 의존성 준비 |
| fmt | Terraform 코드 서식 정리 |
| validate | provider 스키마를 포함한 설정 검사 |
| plan | 실제 계정 상태와 비교해 생성·변경·삭제 예정 확인 |

정상 기준은 validate 성공과 계획에 의도한 team4 리소스가 표시되는 것입니다. 기존 다른 프로젝트 리소스의 삭제·교체가 보이면 apply하지 말고 입력과 state 위치를 확인합니다.

패키지에 포함된 infra/.terraform.lock.hcl을 유지·커밋하여 팀의 provider 버전을 맞춥니다. 의도적인 업데이트가 아니라면 init -upgrade를 사용하지 않습니다. tfstate, tfplan, 실제 tfvars는 커밋하지 않습니다.

## 14 AWS 리소스 생성

계획을 검토한 뒤 인프라 담당자만 실행합니다. 이 명령은 저장된 계획을 곧바로 적용하므로 별도 yes 입력을 기다리지 않습니다.

```bash
terraform -chdir=infra apply team4.tfplan
```

생성에는 여러 분에서 수십 분이 걸릴 수 있습니다. 다른 팀원이 동일 이름으로 별도의 apply를 시작하지 않습니다. 부분 실패가 발생해도 state를 지우지 말고 실패 원인을 고친 뒤 plan으로 상태를 다시 확인합니다.

완료 후 출력과 상태를 확인합니다.

```bash
terraform -chdir=infra output
aws eks describe-cluster --name team4-eks --region ap-northeast-2 --query 'cluster.status' --output text
aws eks describe-nodegroup --cluster-name team4-eks --nodegroup-name demo-workers --region ap-northeast-2 --query 'nodegroup.status' --output text
```

정상 기준은 클러스터와 노드 그룹 ACTIVE입니다. node group의 max_size=2는 자동으로 두 대로 늘린다는 뜻이 아닙니다. 이 예제는 autoscaler를 설치하지 않으며 desired_size는 1입니다.

## 15 공용 EKS 접속과 네트워크 확인

```bash
aws eks update-kubeconfig --name team4-eks --region ap-northeast-2 --alias team4-eks
kubectl config get-contexts
kubectl --context team4-eks get nodes
kubectl --context team4-eks get pods -n kube-system
kubectl --context team4-eks auth can-i create deployments -n demo
```

이 단계는 access entry와 공인 IP가 등록된 팀원이 각자 자신의 AWS 로그인으로 실행합니다. kubeconfig 파일을 팀원끼리 복사하는 방식이 아닙니다.

로컬은 `--context kind-team4`, AWS는 `--context team4-eks`를 붙여 구분합니다. `aws eks update-kubeconfig`는 현재 context를 변경할 수 있으므로 이후 명령에서 context를 생략하지 않는 편이 좋습니다.

EKS에는 로컬 Calico를 추가로 설치하지 않습니다. Terraform이 VPC CNI add-on에 enableNetworkPolicy=true를 설정합니다.

```bash
aws eks describe-addon --cluster-name team4-eks --addon-name vpc-cni --region ap-northeast-2 --query 'addon.{version:addonVersion,status:status,config:configurationValues}'
kubectl --context team4-eks -n kube-system get daemonset aws-node
kubectl --context team4-eks -n kube-system get pods -l k8s-app=aws-node
```

정상 기준은 add-on ACTIVE, 구성의 enableNetworkPolicy=true, aws-node와 network policy agent 준비 상태입니다. 실제 차단 검사는 다음 단계에서 수행합니다.

이 초기 구성은 CNI의 standard mode를 사용합니다. 신규 Pod의 정책 반영 전 일시적인 허용 구간까지 제거하려면 이후 strict mode와 CoreDNS를 포함한 필요 정책을 함께 설계해야 합니다.

또한 시작 단계에서는 AmazonEKS_CNI_Policy를 node role에 연결했습니다. 일반 테스트 Pod는 IMDS hop limit 1과 hostNetwork 미사용으로 노드 메타데이터 접근을 제한합니다. 최종 권한 분리 작업에서는 CNI 전용 IRSA 또는 Pod Identity 역할로 옮기고 node role의 CNI 권한을 제거합니다. ESO 역할 분리와는 별도의 작업입니다.

## 16 ECR 업로드와 digest 기반 배포

이 명령은 로컬 6단계를 완료해 team4-test:v1 이미지가 있는 인프라 담당자가 실행합니다.

```bash
bash scripts/06-push-and-deploy-eks.sh v1
```

스크립트는 다음을 수행합니다.

1. Terraform output에서 ECR 주소와 cluster 이름 읽기.
2. 현재 AWS 계정이 맞는지 확인.
3. 임시 ECR 로그인 토큰을 Docker에 전달.
4. 로컬 이미지에 ECR 태그를 붙여 업로드.
5. ECR에서 업로드된 이미지 digest 조회.
6. 같은 digest를 세 Deployment의 image에 넣어 generated/workloads-eks.yaml 생성.
7. EKS에 namespace와 Deployment·Service 적용.
8. 준비 상태와 client 접속 확인.

로그인 토큰, 자격증명은 YAML에 기록하지 않습니다. ECR에서 이미지를 가져오는 권한은 node role에 있고 ECR 업로드 권한은 실행자의 IAM 권한입니다.

ECR 태그는 IMMUTABLE입니다. 같은 v1 태그로 다시 업로드하면 실패할 수 있습니다. 이미지를 다시 빌드한 다음 v2 등 새 태그를 사용하거나 CI에서는 commit SHA 기반 태그를 사용합니다.

```bash
cat evidence/deployed-image.txt
kubectl --context team4-eks -n demo get deployments,pods,services
kubectl --context team4-eks -n demo get deployment server -o jsonpath='{.spec.template.spec.containers[0].image}'
kubectl --context team4-eks -n demo exec deployment/client -- wget -T 5 -qO- http://server:8080
```

정상 기준은 ECR digest 주소, 세 Deployment 준비 완료, `team4 server ok` 응답입니다. 컨테이너 런타임의 imageID는 멀티아키텍처 manifest의 하위 플랫폼 digest일 수 있으므로 태그 문자열만으로 이미지 동일성을 판단하지 않습니다. 이 예제의 빌드 플랫폼은 linux/amd64로 고정합니다.

EKS CNI도 동일한 시험으로 검증합니다.

```bash
bash scripts/04-cni-smoke-test.sh team4-eks
```

## 17 복구 시연용 보안 그룹 확인

```bash
DEMO_SG_ID=$(terraform -chdir=infra output -raw demo_security_group_id)
aws ec2 describe-security-groups --region ap-northeast-2 --group-ids "$DEMO_SG_ID"
aws ec2 describe-network-interfaces --region ap-northeast-2 --filters "Name=group-id,Values=$DEMO_SG_ID" --query 'NetworkInterfaces[].NetworkInterfaceId'
```

정상 기준은 Project=team4, DemoOnly=true 태그가 있고 network interface 목록이 비어 있는 것입니다. 이 단계에서는 위험한 SSH 규칙을 추가하지 않습니다. Config·Lambda 자동 복구 작업을 만들 때 이 SG만 시연 대상으로 사용합니다.

AWS 전체의 태그 없는 SG나 실제 EKS 클러스터 SG를 시연 대상으로 고르지 않습니다.

## 18 팀원이 공용 EKS에 들어가는 순서

1. 개인 AWS 로그인 준비.
2. 본인의 IAM role/user ARN과 공인 IPv4를 인프라 담당자에게 전달.
3. 담당자가 terraform.tfvars에 access entry 대상과 CIDR 추가.
4. 담당자가 plan 확인 후 apply.
5. 팀원은 자신의 PC에서 aws sso login과 update-kubeconfig 실행.
6. `kubectl --context team4-eks get nodes`와 `auth can-i` 확인.

클러스터 초기화나 정책 변경은 공용 환경에 영향을 줍니다. 개인 실험은 우선 각자의 kind에서 검증하고, 공용 EKS의 demo namespace에는 합의한 YAML을 적용합니다.

## 19 자주 생기는 오류

| 증상 | 먼저 확인할 것 |
|---|---|
| docker 명령 없음 | Docker Desktop 설치, WSL Integration 활성화 |
| Cannot connect to Docker daemon | Docker Desktop 실행 상태와 Ubuntu 연결 |
| kind node NotReady | Calico operator·calico-node 이벤트와 CIDR 일치 |
| 다운로드 404 | config/versions.env와 공식 릴리스 자산 이름 확인 |
| 로컬 ImagePullBackOff | kind load 완료, image 이름, IfNotPresent |
| EKS ImagePullBackOff | ECR digest, node role pull 권한, 외부 통신 |
| Pod Pending | kubectl describe pod의 Events, 노드 CPU·메모리·Pod 수 |
| SSH Permission denied | GitHub 등록 공개키와 현재 사용자 확인 |
| terraform AccessDenied | 오류의 API 이름과 담당자 IAM 권한 확인 |
| EKS API timeout | 현재 공인 IP allowlist, VPN, DNS, endpoint 설정 |
| EKS Unauthorized/Forbidden | 개인 로그인 만료, access entry ARN, policy 연결 |
| node group NodeCreationFailure | 노드 IAM, public IP 할당, route·보안 그룹 |
| server 이름 조회 실패 | CoreDNS, namespace, DNS 정책 |
| CNI 시험에서 계속 접속 성공 | network policy agent, 라벨 일치, 다른 허용 정책 |

공통 진단 명령은 다음과 같습니다. CONTEXT는 kind-team4 또는 team4-eks로 바꿉니다.

```bash
kubectl --context CONTEXT -n demo get pods -o wide
kubectl --context CONTEXT -n demo describe pod POD_NAME
kubectl --context CONTEXT -n demo get events --sort-by=.metadata.creationTimestamp
kubectl --context CONTEXT -n demo logs deployment/server
kubectl --context CONTEXT -n demo get networkpolicy
```

## 20 종료와 삭제

로컬 kind를 삭제하려면 다음 명령을 사용합니다. 해당 로컬 클러스터의 작업이 삭제됩니다.

```bash
kind delete cluster --name team4
```

AWS는 인프라 담당자가 Terraform state를 보유한 폴더에서 삭제 계획을 확인합니다.

```bash
terraform -chdir=infra plan -destroy
terraform -chdir=infra destroy
```

destroy는 yes 확인을 받습니다. ECR은 force_delete=false이므로 이미지가 남아 있으면 저장소 삭제가 거부됩니다. 실패하면 AWS 콘솔 ECR에서 이번 실습 저장소의 이미지와 보관 필요 여부를 검토해 삭제한 후 destroy를 다시 실행합니다. 이미지를 자동으로 일괄 삭제하는 코드는 포함하지 않았습니다.

이후 추가한 LoadBalancer, EBS/PVC, 별도 보안 그룹·endpoint 등이 있으면 관련 Kubernetes 리소스를 먼저 정리해야 VPC 삭제가 가능합니다. 해당 작업이 완료될 때까지 state를 지우지 않습니다.

삭제 완료는 EKS, EC2, EBS, ECR, CloudWatch, VPC에서 해당 프로젝트 리소스가 제거됐는지 확인합니다. 노트북이나 Docker Desktop을 끄는 것으로 AWS가 삭제되지는 않습니다.

## 21 이번 단계 완료 기준

- 각 팀원 PC에서 Docker, CLI, kind 실행 가능.
- 같은 설정의 로컬 Kubernetes 노드가 Ready.
- server, client, unauthorized Deployment가 준비됨.
- 정책 적용 전 연결 성공, 임시 정책으로 한쪽 차단, 삭제 후 복구 확인.
- 팀 GitHub 저장소와 개인 브랜치 사용 가능.
- 지정 담당자가 Terraform으로 팀 공용 EKS 생성.
- 개인 IAM 권한으로 공용 EKS 접속 가능.
- ECR digest 기반으로 같은 테스트 이미지 배포.
- 복구 시연용 SG는 태그가 있고 실제 장비에 연결되지 않음.

## 검증 범위

제공된 파일은 설정·스크립트의 정적 검토용 시작 구성입니다. 작성 환경에서 가능한 문법 검사를 수행했으며, 사용자 PC에서 Docker·kind 실행 및 사용자 AWS 계정에서의 plan/apply·통신 검증은 아직 수행하지 않았습니다. 패키지의 VALIDATION.md에 실제 검사 결과와 제한을 기록합니다. 설치 버전, 계정 권한, 네트워크 환경에 따른 오류는 각 단계의 확인 명령으로 점검합니다.

## 참고 문서

- Microsoft WSL 설치: https://learn.microsoft.com/en-us/windows/wsl/install
- Docker Desktop WSL 연결: https://docs.docker.com/desktop/features/wsl/
- kind Quick Start: https://kind.sigs.k8s.io/docs/user/quick-start/
- Calico kind 설치: https://docs.tigera.io/calico/latest/getting-started/kubernetes/kind
- Calico 호환 범위: https://docs.tigera.io/calico/latest/getting-started/kubernetes/requirements
- kubectl 설치: https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/
- Helm 설치: https://helm.sh/docs/intro/install/
- Terraform 설치: https://developer.hashicorp.com/terraform/install
- AWS CLI 설치: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
- AWS SSO 로그인: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html
- EKS 버전: https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html
- EKS VPC CNI NetworkPolicy: https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html
- EKS 보안 그룹: https://docs.aws.amazon.com/eks/latest/userguide/sec-group-reqs.html
- EKS managed node group: https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html
- CNI 전용 IAM 분리: https://docs.aws.amazon.com/eks/latest/userguide/cni-iam-role.html
- EKS 과금: https://aws.amazon.com/eks/pricing/
