# GitHub CI와 승인된 AWS 배포 설정

대상 저장소는 `realthoroughbred/capstone_1`입니다. 이 문서는 설정 절차이며, GitHub 환경·runner·AWS 역할이 실제로 연결되었다는 증거는 아닙니다. AWS 리소스 생성과 유료 배포는 별도 승인 범위에서 진행합니다.

AWS는 WSL의 `aws login --remote --profile team4 --region ap-northeast-2`로 IAM 사용자 `arn:aws:iam::852093844554:user/team4-operator` 인증을 확인했습니다. SSO 방식이 아닙니다. 서비스 사전 조회 5개는 모두 AccessDenied였으므로 OIDC provider/역할/EKS가 준비됐다고 볼 수 없습니다(`evidence/aws/preflight.json`). 총예산 180,000원 안에서 실제 plan·비용을 검토한 명시적 생성 승인 전에는 AWS 배포 workflow를 실행하지 않습니다. [AWS 준비 절차](../AWS_DEPLOYMENT_GUIDE.md).

현재는 관리자에게 [사전 조회 IAM 정책](TEAM4_IAM_PERMISSIONS.md) 연결을 요청한 단계입니다. GitHub 일반 CI 실행과 AWS 배포 활성화를 구분하며, 개인 `team4` 로그인 cache를 GitHub runner로 복사하지 않습니다.

## 1. 로컬 GitHub 인증과 작업 사본

초기 제공 폴더는 `.git`이 없는 압축본입니다. `git status`가 `not a git repository`를 반환하는 상태에서 push하지 마세요. 기존 저장소를 별도 폴더에 clone하고, 검토한 변경 파일만 작업 브랜치로 옮깁니다. Terraform state, `.aws`, `.kube`, `.env`, 개인키, `evidence/`, 다운로드 파일은 복사하거나 커밋하지 않습니다. 이미 정상 clone한 작업 사본이 있으면 그것을 사용합니다.

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

저장소 관리자/소유자가 **Settings → Environments → New environment**에서 정확히 `aws-demo`를 만듭니다. 워크플로 최초 실행으로 환경을 자동 생성하면 보호 규칙이 없는 환경이 생길 수 있으므로 먼저 설정합니다.

1. **Required reviewers**에 지정된 배포 검토자를 등록합니다. 여러 명을 등록해도 GitHub 기본 동작은 그중 한 명의 승인입니다.
2. **Prevent self-review**를 켭니다.
3. **Allow administrators to bypass configured protection rules**를 끄고 저장합니다.
4. **Deployment branches and tags → Selected branches and tags**에서 **Branch / `main`** 규칙 하나만 추가합니다. 태그 규칙, `*`, `feature/**` 규칙은 추가하지 않습니다.
5. 필요한 검토자 기능이 현재 저장소 공개 범위/요금제에서 제공되지 않으면 배포 워크플로를 활성화하지 않고 그 제약을 먼저 해결합니다. 환경이 존재한다는 사실만으로 승인 기능이 켜진 것은 아닙니다.

GitHub의 환경 보호 기능과 요금제별 제공 범위는 [공식 환경 설정 문서](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)를 확인합니다.

`main`에도 ruleset 또는 branch protection을 설정해 PR 승인, `validate`·`image` CI 성공, force push 제한을 적용합니다. `.github/workflows/`, 배포 스크립트, admission 정책과 Terraform 변경을 검토 대상에 포함합니다. 현재 배포 워크플로는 `workflow_dispatch`와 `github.ref == 'refs/heads/main'` 조건을 사용합니다. 이 조건과 환경의 `main` 전용 정책을 함께 유지합니다.

## 3. 배포 runner 격리

`.github/workflows/checkov.yml`의 PR/일반 CI는 GitHub 호스팅 `ubuntu-24.04`에서 실행합니다. `.github/workflows/deploy.yml`만 `self-hosted`, `linux`, `team4-deploy` 라벨을 사용합니다.

- 배포 runner는 별도의 Linux x86_64 머신/일회용 실행 환경으로 준비하고 PR 작업, 포크 코드, `pull_request_target`의 외부 코드 checkout을 실행하지 않습니다. 배포 runner 라벨만으로 접근 통제가 완성되지는 않습니다.
- 조직 runner group을 사용할 수 있으면 해당 저장소만 허용하고, 지원되는 정책에서 `.github/workflows/deploy.yml@refs/heads/main`만 실행하도록 제한합니다. 개인 공개 저장소에서 동등한 runner 격리를 보장할 수 없다면 외부 PR을 받는 저장소에 AWS 접근 가능한 상시 runner를 연결하지 말고, 보호된 전용 배포 저장소/조직 runner로 옮겨 신뢰 조건을 다시 맞춥니다.
- runner에 개인 AWS profile, 관리자 access key, 다른 프로젝트 kubeconfig를 남기지 않습니다. AWS 권한은 승인 후 OIDC 역할로 받습니다. 작업 종료 후 Docker registry 로그인, 임시 kubeconfig와 작업 파일을 정리하거나 runner 자체를 폐기합니다.
- Docker, AWS CLI v2, Python 3, Bash, curl, kubectl, 필요한 패키지 설치 권한을 준비합니다. 도구 버전은 `config/versions.env`와 `config/security-tools.env`를 따릅니다.
- runner가 EKS API에 접근할 수 있어야 합니다. 승인된 고정 공인 IP `/32` 또는 승인된 사설 연결을 사용합니다. 동적 GitHub 호스팅 runner 때문에 EKS API를 `0.0.0.0/0`에 열지 않습니다.

GitHub는 공개 저장소에서 자체 runner가 외부 PR 코드에 노출되는 위험을 설명합니다. [runner group 접근 제한](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access), [워크플로 보안](https://docs.github.com/en/actions/reference/security/secure-use)

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
| `AWS_ACCOUNT_ID` | 현재 확인한 `852093844554`; 승인한 `infra/terraform.tfvars`와 WSL `aws sts get-caller-identity --profile team4 --query Account --output text`로 대조 | 정확한 12자리 대상 계정 |
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

검토한 브랜치를 PR로 반영한 뒤 CI의 정적 검사·이미지 검사를 확인합니다. 배포는 **Actions → Approved EKS deployment → Run workflow → main**에서 요청하고 지정 검토자가 `aws-demo` job을 승인합니다. runner가 연결되지 않으면 job은 queued 상태이므로 배포 완료로 기록하지 않습니다.

성공 판정에는 OIDC 대상 계정 확인, 실제 ECR digest, signature·SBOM attestation 검증, 세 Deployment rollout, `deployment-runtime.json`의 실제 Pod digest/readiness 검증, HTTP 응답 증거가 모두 필요합니다. `evidence/deployed-image.txt`는 publish 단계에서 작성되므로 그 파일만으로 EKS 배포 성공을 판단하지 않습니다. 워크플로 실패 시 자동 `rollout undo`는 하지 않으며 실패 원인과 검증된 대체 이미지를 먼저 확인합니다.

실행한 GitHub run URL, commit SHA, 승인자, 배포 digest와 artifact를 최종 증거에 기록합니다. GitHub 설정 완료, 로컬 단위 테스트 통과, 실제 AWS 배포 성공은 각각 별도 상태로 관리합니다.
