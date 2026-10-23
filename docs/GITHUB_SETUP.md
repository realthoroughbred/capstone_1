# GitHub CI와 승인된 AWS 배포 설정

**2026-10-23 실행 상태:** `aws-demo` environment와 main 전용 branch 규칙, 배포 변수 3개를 생성·재조회했다. Windows 드라이브와 개인 AWS/Git 자격증명을 공유하지 않는 별도 WSL에 rootless Docker와 일회용 runner를 준비·등록했다. runner는 오프라인이며 배포 job은 아직 실행하지 않았다. GitHub OIDC provider와 배포 IAM 역할은 생성됐고, PR #1의 main 반영 및 실제 노드 배포가 남아 있다. 원본 증적은 `evidence/github/environment-created-20261023.json`, `runner-registration-20261023.json`에 보관한다.

대상 저장소는 `realthoroughbred/capstone_1`입니다. 아래는 재현 절차이며 실제 실행 결과는 위 증적과 [현재 상태](../IMPLEMENTATION_STATUS.md)를 따릅니다. 이번 생성·검증·SG 시연·검증 후 신규 자원 정리는 이미 받은 승인 범위에서 진행하며 같은 승인을 다시 요청하지 않습니다. main 반영 여부와 실행할 commit은 root 작업에서 결정합니다.

AWS는 WSL의 IAM 브라우저 로그인으로 `team4-operator` 인증을 확인했습니다. SSO 방식이 아닙니다. 총예산 180,000원 내 기본 1노드·최대 8시간 생성·검증·SG 시험 및 신규 자원 정리가 승인됐습니다. 초기 IAM·KMS 확인과 신규 VPC 생성 후 DNS 속성 조회 권한에서 중단돼 관리자 후속 정책 연결을 기다립니다. OIDC 역할/EKS 배포 준비도 아직 완료되지 않았습니다. [AWS 준비 절차](../AWS_DEPLOYMENT_GUIDE.md).

현재는 [IAM 권한 문서](TEAM4_IAM_PERMISSIONS.md)에 따라 추가 provisioning 권한과 실제 plan을 준비하는 단계입니다. GitHub 일반 CI 실행과 AWS 배포 활성화를 구분하며, 개인 `team4` 로그인 cache를 GitHub runner로 복사하지 않습니다.

## 1. 로컬 GitHub 인증과 작업 사본

초기 제공 폴더는 `.git`이 없는 압축본이었지만 현재는 저장소 이력을 연결하고 작업 브랜치를 push했습니다. 현재 작업 사본을 다시 clone할 필요는 없습니다. `git status`와 branch를 확인하고 이어서 작업합니다. 아래 clone 예시는 새 PC용입니다. Terraform state, `.aws`, `.kube`, `.env`, 개인키, `evidence/`, 다운로드 파일은 복사하거나 커밋하지 않습니다.

GitHub 인증은 기존 GCM 세션으로 실제 API 조회까지 **VERIFIED**했습니다. 저장소는 private이고 저장소 ID는 `1378935906`, 소유자 ID는 `272421931`이며 현재 계정의 admin/push 권한을 확인했습니다. 제한된 실행 세션의 `wincredman` 오류는 일반 권한으로 재검증해 해결했으며 토큰을 출력하거나 파일에 저장하지 않았습니다. `gh`는 PATH에 없지만 현재 인증을 다시 할 필요는 없습니다. 아래 로그인 명령은 다른 PC 또는 인증 만료 시 **본인의 일반 PowerShell 창**에서 사용합니다.

Git for Windows/GCM 경로:

```powershell
git credential-manager --version
git credential-manager github login
git credential-manager github list
git clone https://github.com/realthoroughbred/capstone_1.git capstone_1-work
Set-Location capstone_1-work
git switch -c feature/devsecops-self-healing
```

GCM의 `github login/list`는 GitHub 계정 인증 관리 명령입니다. `wincredman` 오류가 일반 사용자 세션에서도 계속되면 Windows Credential Manager 서비스/사용자 프로필과 Git for Windows 설치를 복구한 뒤 다시 로그인합니다. 평문 credential store로 우회하지 않습니다. [GCM 공식 계정 관리](https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/multiple-users.md)

GitHub CLI를 설치한 뒤 사용할 대안:

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
gh auth status --hostname github.com
gh repo view realthoroughbred/capstone_1 --json nameWithOwner,viewerPermission
```

브라우저 인증을 완료한 뒤 마지막 명령으로 저장소와 자신의 권한을 확인합니다. `gh auth token`, `git credential fill`처럼 토큰을 출력하는 명령은 실행하지 않습니다. GCM과 CLI 중 작업 환경에 맞는 인증 방식을 선택하며, WSL에서 작업하면 해당 WSL 세션의 Git 인증도 별도로 확인합니다. [GitHub CLI 인증](https://cli.github.com/manual/gh_auth_login)

## 2. `aws-demo` 환경의 승인과 브랜치 제한

마지막 GitHub environments 조회 결과는 `total_count=0`이며 **`aws-demo` 환경 설정은 아직 검증되지 않았습니다.** 일반 CI 성공을 배포 보호 설정 완료로 해석하지 않습니다. 실행 전 실제 환경 설정을 확인합니다.

저장소 관리자/소유자가 **Settings → Environments → New environment**에서 정확히 `aws-demo`를 만듭니다. 워크플로 최초 실행으로 환경을 자동 생성하면 보호 규칙이 없는 환경이 생길 수 있으므로 먼저 설정합니다.

이번 1인 실습에서는 대화에 남은 명시적 승인, 검토한 commit, 수동 dispatch 실행자를 증거로 기록합니다. **Required reviewers를 이번 실습의 필수 조건으로 두지 않습니다.** 독립된 검토자가 없는 상태에서 유일한 실행자를 reviewer로 지정하고 **Prevent self-review**까지 켜면 누구도 job을 승인할 수 없습니다. GitHub의 별도 reviewer 승인 없이 진행했다면 결과에도 그대로 기록합니다.

1. **Deployment branches and tags → Selected branches and tags**에서 **Branch / `main`** 규칙 하나만 추가합니다. 태그 규칙, `*`, `feature/**` 규칙은 추가하지 않습니다.
2. 아래의 환경 변수 세 개를 등록하고, 저장된 main 전용 규칙을 다시 조회합니다.
3. 검토된 코드가 main에 반영되고 CI가 통과한 뒤 **Run workflow → main**으로 한 번 실행합니다. 승인 기록과 예산·시간 범위는 기존 결정을 따릅니다.

여러 사람이 운영하는 환경에서는 독립된 **Required reviewers**, **Prevent self-review**, 관리자 보호 규칙 우회 금지를 권장합니다. 이것은 이번 승인된 1인 실습에 추가 승인을 요구하는 조건이 아닙니다. 이미 적용된 조직 규칙은 그대로 준수합니다.

private 저장소의 환경·브랜치 제한과 required reviewers는 요금제별 제공 범위가 다릅니다. reviewer 기능 부재만으로 이번 실습을 중단할 필요는 없지만, **환경의 main 제한 자체를 적용할 수 없다면 현재 environment 기반 IAM 신뢰 조건으로 배포하지 않습니다.** 이 경우 미지원 상태를 기록하고 실행 경로를 검토하며, wildcard나 무보호 환경으로 우회하지 않습니다. [공식 환경 설정 문서](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)

`main` 반영 전에는 PR의 `validate`·`image` CI와 `.github/workflows/`, 배포 스크립트, admission 정책, Terraform 변경을 검토합니다. 팀 운영에서는 ruleset/branch protection의 독립 PR 승인과 force push 제한을 추가합니다. 이번 개인 실습의 main 반영은 root가 검토 상태에 따라 결정합니다. 현재 배포 워크플로의 `workflow_dispatch`, `github.ref == 'refs/heads/main'`, 환경의 main 전용 규칙과 main 서명 identity는 모두 유지합니다. 로컬 브라우저 로그인이나 `COSIGN_IDENTITY` 환경변수 변경으로 GitHub main workflow 인증서를 대신 만들 수 없습니다.

## 3. 일회성 WSL 배포 runner

`.github/workflows/checkov.yml`의 PR/일반 CI는 GitHub 호스팅 `ubuntu-24.04`에서 실행합니다. `.github/workflows/deploy.yml`만 `self-hosted`, `linux`, `x64`, `team4-deploy` 라벨을 사용합니다.

이번 경로는 현재 PC의 WSL Linux x86_64에서 **배포 job 한 개만 실행**합니다. 신규 EC2 runner를 만들지 않으므로 그에 따른 EC2 비용은 없고, PC의 CPU·메모리·디스크를 사용합니다. EKS·ECR 등 AWS 자원과 GitHub 요금제/사용량은 기존 예산·실행 범위에서 별도로 계산합니다. 상시 서비스 설치나 자동 시작은 하지 않습니다.

전용 Linux 사용자로 로그인해 새 HOME·작업 디렉터리를 사용하고 `actions/checkout`으로 코드만 받습니다. 개인 `.aws`/login cache, `.kube`, GCM·SSH 설정, Terraform state·tfvars를 복사하거나 읽을 수 있게 두지 않습니다. 개인 AWS/GitHub credential 환경변수·SSH agent를 상속하지 않고, `AWS_CONFIG_FILE`·`AWS_SHARED_CREDENTIALS_FILE`은 빈 전용 파일, `KUBECONFIG`는 새 전용 경로, `DOCKER_CONFIG`는 빈 전용 디렉터리로 지정합니다. `AWS_EC2_METADATA_DISABLED=true`로 metadata 자격 증명 탐색도 막고, AWS 권한은 job의 OIDC 역할에서만 받습니다.

**전용 사용자·HOME 변경·컨테이너만으로 완전한 격리가 되지는 않습니다.** Windows 자동 마운트나 공유 Docker daemon 소켓으로 개인 파일에 접근할 수 있으면 별도 일회성 WSL 배포판을 사용합니다. 그 배포판에서는 Windows 자동 마운트·실행 파일 연동을 끄고 개인 디렉터리나 기존 Docker 소켓을 연결하지 않습니다. Docker는 전용 rootless daemon 또는 개인 파일이 없는 별도 WSL 내부 daemon을 사용합니다. 기존 작업용 Ubuntu 설정은 변경하지 않습니다. [WSL 설정](https://learn.microsoft.com/en-us/windows/wsl/wsl-config), [Docker daemon 권한](https://docs.docker.com/engine/security/)

Docker, AWS CLI v2, Python 3, Bash, curl, kubectl과 runner 라이브러리를 미리 준비하며 runner 자체는 root로 실행하지 않습니다. 도구 버전은 `config/versions.env`와 `config/security-tools.env`를 따릅니다. GitHub·ECR·Sigstore HTTPS와 승인된 EKS API `/32` 접근이 필요하며 endpoint를 `0.0.0.0/0`으로 넓히지 않습니다. 저장소 **Settings → Actions → Runners → New self-hosted runner → Linux / x64**의 현재 패키지·체크섬으로 준비한 뒤 등록 형태는 다음과 같습니다. 토큰은 등록 프롬프트에만 입력합니다.

```sh
./config.sh --url https://github.com/realthoroughbred/capstone_1 \
  --name team4-deploy-once --labels team4-deploy --work _work --ephemeral
./run.sh
```

기본 `self-hosted`, `linux`, `x64` 라벨에 `team4-deploy`를 추가합니다. 검토한 main 배포 한 건에만 연결하고 PR/포크 코드나 다른 queued 작업을 실행하지 않습니다. 라벨 자체는 접근 통제가 아니며, 조직 runner group이 있으면 저장소·workflow도 제한합니다. [runner 접근 제한](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access)

`--ephemeral`은 job 한 개 뒤 등록을 해제하지만 **로컬 파일은 삭제하지 않습니다.** 성공·실패 모두 artifact/진단 기록을 보존하고 종료·등록 해제를 확인한 뒤, 이번 실행의 ECR 로그인·kubeconfig·작업 디렉터리·전용 Docker 데이터 또는 일회성 WSL만 정리합니다. 원래 profile·kubeconfig·state·로컬 클러스터는 보존합니다. [GitHub 일회성 runner 동작](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)

## 4. AWS OIDC와 Kubernetes 권한

승인된 Terraform 설정에서 `enable_github_deploy=true`, `github_repository="realthoroughbred/capstone_1"`, `github_subject_prefix="repo:realthoroughbred@272421931/capstone_1@1378935906"`, `github_environment="aws-demo"`를 사용합니다. 계정에 GitHub OIDC provider가 이미 있으면 `existing_github_oidc_provider_arn`으로 재사용합니다. 새 계정/역할 생성은 승인된 plan/apply 범위에 포함되어야 합니다.

대상 저장소의 API 조회 결과 `use_default=true`, `use_immutable_subject=true`이고 확인한 subject prefix는 `repo:realthoroughbred@272421931/capstone_1@1378935906`입니다. `aws-demo`에 필요한 정확한 신뢰 조건은 다음과 같습니다.

```text
aud = sts.amazonaws.com
sub = repo:realthoroughbred@272421931/capstone_1@1378935906:environment:aws-demo
```

환경을 사용하는 OIDC subject에는 기본적으로 브랜치가 들어가지 않으므로 GitHub 환경의 `main` 제한이 필요합니다. **이 저장소에는 ID가 없는 과거의 `repo:realthoroughbred/capstone_1:environment:aws-demo` 조건을 사용하면 안 됩니다.** 다른 저장소로 옮기면 그 저장소의 API 설정/ID를 확인하고 Terraform 신뢰 조건을 다시 맞춥니다. 맞지 않는다고 `repo:*` 등의 wildcard로 넓히지 않습니다. JWT 원문은 출력하거나 보관하지 않습니다. [GitHub AWS OIDC 설정](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)

EKS access entry는 이 역할을 `team4:deploy` 그룹에 연결합니다. 운영자 bootstrap에서 해당 Kubernetes RBAC, `demo` namespace, NetworkPolicy, ESO, Kyverno 정책을 먼저 설치합니다. 배포 역할은 이 정책을 약화시키거나 클러스터를 생성하는 역할이 아닙니다. 일반 배포에는 demo의 Deployment/Service 변경, Pod·ReplicaSet 읽기 및 HTTP 검사용 Pod exec 권한이 필요합니다. Inspector의 `team4:image-remediator` 역할은 별도로 유지합니다.

## 5. GitHub 환경 변수 매핑

**Settings → Environments → aws-demo → Environment variables**에 다음 세 값을 등록합니다. 장기 AWS access key/secret key를 GitHub Secrets에 추가하지 않습니다.

| GitHub 변수 | 값의 출처 | 주의점 |
| --- | --- | --- |
| `AWS_ACCOUNT_ID` | 현재 확인한 `852093844554`; 운영자 작업 사본의 승인된 tfvars와 WSL `aws sts get-caller-identity --profile team4 --query Account --output text`로 대조 | 정확한 12자리 대상 계정 |
| `AWS_DEPLOY_ROLE_ARN` | `terraform -chdir=infra output -raw github_deploy_role_arn` | 자동복구/관리자 역할이 아닌 GitHub 배포 역할 |
| `ECR_REPOSITORY` | `terraform -chdir=infra output -raw repository_url` | `ACCOUNT.dkr.ecr.ap-northeast-2.amazonaws.com/team4-test` 형태의 **전체 URL** |

`repository_name` 출력은 Inspector Lambda용 이름이며 GitHub 변수에 넣을 값이 아닙니다. 현재 워크플로의 region은 `ap-northeast-2`, cluster는 `team4-eks`, 서명 identity는 `https://github.com/realthoroughbred/capstone_1/.github/workflows/deploy.yml@refs/heads/main`으로 고정되어 있습니다. 계정·리전·저장소를 바꾸면 워크플로, Terraform, Kyverno 서명 정책, Inspector의 signature identity를 함께 검토합니다.

관리자가 CLI로 같은 값을 등록할 때의 예입니다. AWS 인증은 WSL에 있으므로 WSL에서 조회하고, Windows의 GCM/`gh` 인증은 Windows에서 사용합니다. 실제 Terraform state가 있는 **Windows·WSL 공유 저장소 루트**에서 Windows PowerShell을 열고 실행하며, `gh`가 설치·인증된 관리자 설정 단계에만 해당합니다. 이 명령은 GitHub 설정을 실제로 변경합니다. WSL 전용 경로에 state가 있다면 해당 경로의 WSL 터미널에서 output을 조회하여 콘솔에 등록합니다.

```powershell
$deployAccount = wsl -d Ubuntu -- aws sts get-caller-identity --profile team4 --region ap-northeast-2 --query Account --output text
if ($LASTEXITCODE -ne 0 -or $deployAccount.Trim() -ne '852093844554') { throw 'AWS account check failed' }
$deployRole = wsl -d Ubuntu -- terraform -chdir=infra output -raw github_deploy_role_arn
if ($LASTEXITCODE -ne 0 -or $deployRole -notmatch '^arn:aws:iam::852093844554:role/') { throw 'Deployment role output unavailable' }
$deployRepository = wsl -d Ubuntu -- terraform -chdir=infra output -raw repository_url
if ($LASTEXITCODE -ne 0 -or $deployRepository -notmatch '^852093844554\.dkr\.ecr\.ap-northeast-2\.amazonaws\.com/') { throw 'ECR output unavailable' }
gh variable set AWS_ACCOUNT_ID --repo realthoroughbred/capstone_1 --env aws-demo --body "$deployAccount"
gh variable set AWS_DEPLOY_ROLE_ARN --repo realthoroughbred/capstone_1 --env aws-demo --body "$deployRole"
gh variable set ECR_REPOSITORY --repo realthoroughbred/capstone_1 --env aws-demo --body "$deployRepository"
gh variable list --repo realthoroughbred/capstone_1 --env aws-demo
```

명령을 실행하기 전에 `$deployAccount`가 승인한 Terraform 계정과 같은지 대조하고, output 명령이 성공했으며 값이 빈 문자열/`null`이 아닌지 확인합니다. [환경 변수 CLI](https://cli.github.com/manual/gh_variable_set)

## 6. 첫 실행과 성공 판정

일반 CI는 [run 39116090770](https://github.com/realthoroughbred/capstone_1/actions/runs/39116090770), commit `dd13627053f4b76af4ec151894946f5b6509f37f`에서 실제 통과했습니다. artifact의 Python 70개, Terraform mock 6개, Checkov 111 passed/0 failed/23 skipped를 확인했습니다. 이 결과는 AWS 배포 job 실행이나 `aws-demo` 설정 완료 증거가 아닙니다. 후속 변경은 해당 commit의 CI로 새로 검증합니다.

후속 [run 39116901979](https://github.com/realthoroughbred/capstone_1/actions/runs/39116901979)도 통과했고 Terraform mock은 8개입니다. 변경은 [draft PR #1](https://github.com/realthoroughbred/capstone_1/pull/1)에서 검토합니다. 마지막 문서 변경 뒤의 commit·PR CI 상태는 별도로 확인합니다.

검토한 브랜치를 PR로 main에 반영한 뒤 해당 commit의 정적 검사·이미지 검사를 확인합니다. `workflow_dispatch` 파일은 default branch에 있어야 합니다. 배포는 **Actions → Approved EKS deployment → Run workflow → main**에서 실행합니다. 이번 실습은 기존 대화 승인 기록과 수동 dispatch를 사용하고, 별도 reviewer를 구성한 운영 환경에서만 그 reviewer 단계도 수행합니다. runner가 연결되지 않으면 job은 queued 상태이므로 배포 완료로 기록하지 않습니다. [수동 workflow 실행](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

성공 판정에는 OIDC 대상 계정 확인, 실제 ECR digest, signature·SBOM attestation 검증, 세 Deployment rollout, `deployment-runtime.json`의 실제 Pod digest/readiness 검증, HTTP 응답 증거가 모두 필요합니다. `evidence/deployed-image.txt`는 publish 단계에서 작성되므로 그 파일만으로 EKS 배포 성공을 판단하지 않습니다. 워크플로 실패 시 자동 `rollout undo`는 하지 않으며 실패 원인과 검증된 대체 이미지를 먼저 확인합니다.

실행한 GitHub run URL, commit SHA, 기존 승인 기록, dispatch 실행자, 배포 digest와 artifact를 최종 증거에 기록합니다. 별도 reviewer 승인이 있었다면 그 기록도 추가합니다. GitHub 설정 완료, 로컬 단위 테스트 통과, 실제 AWS 배포 성공은 각각 별도 상태로 관리합니다. 이 문서 수정만으로 환경 생성·runner 등록·main 병합·AWS 배포를 실행한 것은 아닙니다.
