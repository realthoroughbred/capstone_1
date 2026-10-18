# Kubernetes 실행과 검증

실행 환경은 Bash/WSL Ubuntu이며 모든 스크립트가 명시적 `kind-team4` 또는 `team4-eks` context와 `demo` 네임스페이스의 `project=team4` 라벨을 확인한다. 이 문서는 실행 순서와 판정 방법이다. 실제 성공 여부는 `evidence/` 로그와 최종 검증 보고서를 확인한다.

## 로컬 실행 순서

기존 클러스터가 있으면 재생성하지 않는다. 처음 준비하는 경우에만 `02-local-cluster.sh`, `03-local-workloads.sh`를 실행한다.

```bash
kubectl --context kind-team4 apply -f k8s/namespace.yaml
bash scripts/08-network-policy-test.sh kind-team4
bash scripts/07-install-security-addons.sh kind-team4 eso
bash scripts/09-eso-test.sh kind-team4 fake
bash scripts/07-install-security-addons.sh kind-team4 kyverno
bash scripts/10-admission-test.sh kind-team4
bash scripts/validate-kyverno-schema.sh kind-team4
bash scripts/07-install-security-addons.sh kind-team4 argocd
```

기존 ESO가 같은 고정 버전으로 설치되어 있으면 ESO 설치 단계는 생략한다. 고정 Helm chart는 `config/security-versions.env`의 ESO 2.13.0, Kyverno 3.9.1 (애플리케이션 1.19.1), Argo CD 9.5.10 (애플리케이션 3.3.8)이다. Helm의 `--wait` 성공과 실제 정책/통신 검증 성공은 별도로 판단한다. 단일 admission replica는 비용 절감용 실습 설정이다.

Argo CD ApplicationSet은 고정 chart에서 `applicationSet.replicas=0`으로 중지한다. 이 chart에 존재하지 않는 `applicationSet.enabled` 옵션으로 중지했다고 판단하지 않는다.

## NetworkPolicy

Git의 기준 경로는 `policies/network`이다. 모든 Pod에 ingress와 egress 기본 차단을 적용하고, DNS는 `kube-system`의 `k8s-app=kube-dns` Pod TCP/UDP 53만 허용한다. `client`의 egress와 `server`의 ingress를 각각 TCP 8080으로 허용한다. NodeLocal DNS를 사용하는 환경은 별도 목적지 규칙이 필요하다. 로컬 Calico와 EKS VPC CNI의 구현은 다르므로 두 환경에서 각각 실제 데이터 경로를 테스트한다.

`08`은 DNS 성공, 동일 서버 IP로 client 성공, unauthorized 실패를 확인한다. 이후 시험 전용 정책으로 ingress만 허용한 상태의 egress 차단, 양방향 허용 상태의 성공, egress만 허용한 상태의 ingress 차단을 각각 검증한다. 임시 허용은 `EXIT` trap에서 제거한다. 정상 Pod의 exec 성공과 서버에 대한 성공 대조군, 반복 실패를 함께 확인하여 일반 연결 오류를 차단 성공으로 오인하지 않게 한다. 최종 기본 차단 정책은 유지한다. `--verify-only`는 어떤 정책도 수정하지 않는다.

## ESO와 IRSA

`external-secrets.io/v1` API를 사용한다. 로컬 Fake Provider는 시험 데이터 전용이며 실제 자격증명을 저장하지 않는다. `09`는 Kubernetes Secret과 실행 중인 `secret-reader` Pod 볼륨 내용이 같은지 내부 해시로 비교하고, 생성한 임의 시험 값으로 갱신한 뒤 두 위치에 모두 새 값이 전달되는지 최대 180초간 확인한다. 값과 해시를 로그에 출력하지 않는다. `subPath`를 쓰지 않아 kubelet의 Secret 갱신 전파를 지원한다. 환경변수 주입은 자동 갱신되지 않으므로 이 시험은 볼륨 주입을 검증한다.

EKS에서는 `demo/eso-secrets-reader` ServiceAccount와 namespaced SecretStore의 `jwt.serviceAccountRef`를 사용한다. Terraform `eso_role_arn`은 이 ServiceAccount만 신뢰하고, `demo_secret_arn`에 대한 읽기 및 해당 KMS 키의 제한된 복호화만 허용한다. 컨트롤러 공용 자격증명이나 AWS 장기 키가 필요하지 않다.

```bash
# 승인된 EKS가 준비된 뒤 관리자 권한으로 실행
bash scripts/07-install-security-addons.sh team4-eks all
bash scripts/12-configure-eks-security.sh
export ESO_ROLE_ARN="$(terraform -chdir=infra output -raw eso_role_arn)"
export DEMO_SECRET_ARN="$(terraform -chdir=infra output -raw demo_secret_arn)"
export AWS_REGION=ap-northeast-2
# Secrets Manager의 전용 시험 secret에 {"token":"<임의 시험 값>"}를 먼저 입력한다.
bash scripts/09-eso-test.sh team4-eks aws
# 전용 시험 Secret 갱신까지 승인된 경우에만 실행
bash scripts/09-eso-test.sh team4-eks aws --rotate-demo
```

`--rotate-demo`는 현재 Terraform state의 secret ARN과 현재 AWS 계정을 확인한 뒤 값만 갱신한다. 값은 0600 임시 파일을 거쳐 전달하고 삭제하며 Terraform state에 넣지 않는다. 기존 Secret 버전이 전혀 없는 경우 초기 값 입력을 먼저 해야 한다. `09`의 성공은 자동 Secrets Manager rotation Lambda를 구축했다는 의미가 아니다.

## 배포 admission

정책의 PSS 규칙 버전은 `v1.32`로 고정한다. 실제 설치한 Kyverno 1.19.1 CRD는 `v1.35`를 허용하지 않았으며, 클러스터 Kubernetes/EKS 1.35 버전과 Kyverno가 제공하는 PSS 규칙 버전은 서로 독립적이다.

`team4-restricted`는 restricted Pod Security Standard와 모든 일반/init/ephemeral 컨테이너의 읽기 전용 루트 파일시스템을 검사한다. Deployment 검사는 Kyverno의 autogen 규칙을 사용한다. EKS의 `team4-approved-images`는 지정 ECR 저장소와 정확한 SHA256 digest를 요구하며 `team4-verify-signatures`는 다음 GitHub 워크플로 신원, issuer, Rekor 서명을 검증한다.

`https://github.com/realthoroughbred/capstone_1/.github/workflows/deploy.yml@refs/heads/main`

다른 브랜치에서 생성한 서명은 이 배포 신원과 일치하지 않는다. Kyverno admission ServiceAccount에는 특정 ECR 읽기 전용 IRSA를 연결한다. `12`는 이를 반영하기 위해 admission Deployment를 재시작한다. `10`은 실제 서버 dry-run admission 요청으로 정상 Pod 허용과 root/privileged/권한 상승/쓰기 가능한 루트 금지를 확인한다. 로컬 보안 컨텍스트 검증만으로 ECR keyless 서명 검증을 성공 처리하지 않는다. 서명된 이미지에 대한 정상 대조군이 먼저 성공해야 음성 시험을 진행한다. EKS의 unsigned 시험에는 실제 존재하는 미서명 ECR digest를 `UNSIGNED_TEST_IMAGE`로 지정한다. 지정하지 않으면 `NOT_TESTED`로 기록한다.

## GitOps와 실제 복구

네트워크 정책은 Kyverno가 수정하지 않는다. GitOps는 Argo CD가 담당하므로 admission 거절과 drift 복구를 혼동하지 않는다. private GitHub 저장소는 읽기 전용 deploy key를 사용한다. Windows Git Credential Manager가 연결된 환경에서는 다음을 실행한다.

```powershell
python scripts/configure-gitops-auth.py --context kind-team4 --wsl
```

읽기 전용 사전 진단은 같은 명령에 `--inspect-only`를 추가한다. 기존 deploy key의 ID/이름/권한만 조회하며 새 키를 생성하지 않는다. GitHub가 거절하면 자격증명과 요청 값이 제거된 `message`/`errors` 필드를 표시하고 자동 재시도하지 않는다.

이 명령은 GitHub 읽기 전용 deploy key를 생성하고 개인 키를 Argo CD repository Secret으로 직접 전달한다. 개인 키 파일은 임시 디렉터리에만 존재한다. GitHub 토큰은 저장하거나 출력하지 않는다. repository Secret이 이미 있으면 키를 재발급하지 않는다. GitHub Settings → Deploy keys에서 `team4-argocd-<context>` 키와 Secret annotation의 ID를 대조할 수 있다. 클러스터 정리 시 이 키도 사용자 승인 후 제거한다.

```bash
# policies/network가 포함된 실제 원격 commit을 push한 후 실행한다.
export GITOPS_REPO_URL=git@github.com:realthoroughbred/capstone_1.git
export GITOPS_REVISION=<원격에_존재하는_40자리_commit_SHA>
bash scripts/11-gitops-drift-test.sh kind-team4
```

AppProject는 해당 저장소에서 `demo`의 NetworkPolicy만 관리하도록 제한한다. 시험은 먼저 해당 commit의 `Synced` 상태를 확인한다. 자동 동기화를 잠시 끄고 client 허용 ingress를 빈 규칙으로 바꾼 뒤 변경 admission 성공, `OutOfSync`, 정상 서버에 대한 client 통신 실패를 관찰한다. 이후 자동 동기화를 다시 켜서 Argo CD의 새로운 `Succeeded` sync operation, 정확한 commit SHA, 원래 spec 복구, 실제 client 통신 복구를 확인한다. 복구 중 `kubectl apply`로 정책을 수동 재적용하지 않는다. 자동 동기화 설정은 실패 시에도 복원하며, 실패한 검증을 성공으로 기록하지 않는다.

## 증적과 경계

### GitHub deploy key가 금지된 저장소의 로컬 검증

실제 GitHub 응답 `Deploy keys are disabled for this repository`가 확인되었다. 저장소 보안 설정을 바꾸거나 사용자 토큰을 Argo CD에 저장하지 않는다. 직접 GitHub 연동은 승인된 GitHub App 또는 읽기 전용 자격증명이 준비될 때까지 `BLOCKED`다.

로컬 Argo CD 복구 기능은 정확한 원격 게시 commit의 로컬 Git 객체를 복제한 읽기 전용 mirror로 별도 검증할 수 있다.

```bash
export GITOPS_REVISION=<게시가_확인된_40자리_commit_SHA>
bash scripts/prepare-local-gitops-mirror.sh
export GITOPS_REPO_URL=http://team4-git-mirror.argocd.svc.cluster.local:8080/repo.git
bash scripts/11-gitops-drift-test.sh kind-team4
```

mirror는 `kind-team4`에서만 생성하며, commit과 전체 도달 가능한 Git 객체를 담은 900,000 byte 이하 archive를 immutable ConfigMap으로 전달한다. 일반 HTTP Git 전송에는 shallow 저장소를 사용하지 않는다. `argocd`의 HTTP Pod는 읽기 전용 볼륨을 제공하며 외부 엔드포인트가 없는 ClusterIP Service를 쓴다. NetworkPolicy는 같은 네임스페이스의 Argo repo-server에서 TCP8080으로 접근하는 것만 허용하며 mirror egress는 모두 차단한다. 실제 repo-server의 `git ls-remote` 결과와 지정 SHA가 일치해야 mirror 준비를 성공 처리한다. `evidence/gitops-local-mirror.json`에 commit과 archive 해시를 남긴다. 이 검증은 로컬 mirror의 자동 복구 증거이며 직접 GitHub 인증·동기화 성공으로 표시하지 않는다.

- `evidence/network-<context>.log/json`: 실제 연결과 최종 정책. 이 JSON은 정책 상태이며 테스트 결과 JSON은 아니다. 복구 후 무변경 확인은 별도 `network-<context>-verify-only.log`를 사용하여 기존 양방향 분리 시험 증거를 보존한다.
- `evidence/eso-<context>.log/json`: Secret/Pod 일치와 rotation 검사, ExternalSecret 상태. Secret 원문 없음.
- `evidence/admission-<context>.log/json`: admission의 테스트별 PASS/FAIL/NOT_TESTED 및 실제 오류 응답.
- `evidence/gitops-<context>.log/json`: drift, 탐지, 복구, 실제 경과 시간 및 controller operation.
- `evidence/addons-<context>.json`: Helm 설치 상태. 기능 검증을 대신하지 않는다.

공식 근거: [ESO Fake](https://external-secrets.io/latest/provider/fake/), [ESO AWS Secrets Manager](https://external-secrets.io/latest/provider/aws-secrets-manager/), [Kyverno 서명 검증](https://kyverno.io/docs/policy-types/cluster-policy/verify-images/sigstore/), [Argo CD 자동 복구](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/), [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/).
