# 관리자에게 지금 필요한 초기 작업

대상: **계정 852093844554 / 서울 ap-northeast-2 / IAM 사용자 team4-operator**.

사용자는 예산 180,000원 안에서 신규 생성, 최대 8시간 검증, DemoOnly SG TCP 22 시험, 신규 자원 정리를 승인했습니다. **초기 설치 및 CNI/OIDC 정책 수정은 확인 완료입니다.** 현재 `generated/team4-node-s3-admin-20261023.zip` 안의 `먼저읽기.txt`대로 기존 `team4-operator-new-resource-bootstrap` 정책 하나를 교체·기본 버전 저장하면 됩니다. 새 정책·KMS 키·사용자 재연결이나 runtime boundary 수정은 필요 없습니다. 아래 최초 설치 절차는 기록으로 보존합니다.

검토할 파일은 프로젝트의 **`generated/admin-bootstrap/initial/`** 안에 있습니다. 이 폴더는 Git에 올라가지 않으므로 7개 JSON과 manifest를 직접 받거나 [생성 절차](TEAM4_ADMIN_BOOTSTRAP.md)를 사용합니다. **7개 JSON은 IAM 정책 6개 + KMS 생성 입력 1개**입니다.

| JSON 파일 | IAM 정책 이름 | team4-operator에 연결? |
|---|---|---|
| `runtime-boundary.json` | `team4-runtime-boundary` | **연결하지 않음.** 프로젝트 role의 permissions boundary로만 사용 |
| `operator-provisioning.json` | `team4-operator-provisioning` | 연결 |
| `operator-config-only.json` | `team4-operator-config-only` | 연결. Inspector/ECR registry 변경 제외 |
| `operator-demo-validation.json` | `team4-operator-demo-validation` | 연결. 합성 테스트 secret에 한정 |
| `operator-evidence-session.json` | `team4-operator-evidence-session` | 연결. 지정 증적 버킷·프로젝트 Config rule에 한정 |
| `operator-new-github-provider.json` | `team4-operator-new-github-provider` | 연결. 사전 부재 확인된 GitHub issuer 하나에 한정 |
| `kms-create-key.json` | IAM 정책 아님 | 아래 명령의 입력으로 사용 |

1. IAM 콘솔 **정책 → 정책 생성 → JSON**에서 위 6개 정책을 해당 이름으로 만듭니다. 오류를 해결하고 저장합니다. 같은 이름의 기존 정책은 임의로 덮어쓰지 않습니다.
2. **사용자 → team4-operator → 권한 → 권한 추가 → 직접 정책 연결**에서 표의 연결 대상 **5개만** 선택합니다. 기존 `team4-operator-preflight`를 포함하면 사용자 관리형 정책은 **6개**입니다. 다음 단계의 정확한 신규 SG/OIDC bootstrap 정책까지 연결하면 **7개**로 기본 10개 한도 안입니다. 경계 정책은 이 개수에 포함하지 않습니다.
3. 관리자의 기존 AWS 인증 프로필에서 아래 명령으로 **신규 프로젝트 KMS 키 한 개**를 만듭니다. `team4-admin`은 관리자가 사용하는 프로필 이름으로 바꿉니다. 이 입력은 검토된 Terraform plan의 KMS 정책과 태그로 생성했습니다.

```sh
aws sts get-caller-identity --profile team4-admin
aws kms create-key --profile team4-admin --region ap-northeast-2 \
  --cli-input-json file://generated/admin-bootstrap/initial/kms-create-key.json \
  --output json > generated/admin-bootstrap/kms-created.json
```

관리자가 돌려줄 것은 **정책 생성·연결 완료 여부, 신규 KMS의 `KeyMetadata.KeyId`와 생성 메타데이터 파일**입니다. 로그인 토큰·액세스 키·비밀키는 전달하지 않습니다. KMS 원본 키 소재는 이 응답에 포함되지 않습니다.

초기 연결 후 운영자가 신규 네트워크/control plane을 만들고 정확한 SG/subnet/OIDC 식별자를 제공합니다. 관리자는 그때 생성되는 좁은 범위의 bootstrap 정책과 CNI boundary 버전을 검토·연결합니다. 기존 VPC·SG·OIDC의 권한 확대는 하지 않습니다. 단계별 명령과 정리 범위는 [전체 관리자 안내](TEAM4_ADMIN_BOOTSTRAP.md)에 있습니다.
