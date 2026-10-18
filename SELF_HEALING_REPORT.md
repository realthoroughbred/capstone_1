# Self-Healing 구현 및 검증 보고서

복구 코드와 로컬 테스트는 구현했으며, **AWS에서 실제 탐지·복구·EKS 교체를 검증한 결과는 아직 없다.** WSL에서 IAM 브라우저 로그인(`aws login --remote --profile team4 --region ap-northeast-2`) 후 계정 `852093844554`, 사용자 `arn:aws:iam::852093844554:user/team4-operator`의 STS 인증은 확인했다. SSO 로그인은 사용하지 않았다. EKS/EC2/Config/ECR/IAM 사전 조회 5개가 모두 AccessDenied였으며 증적은 `evidence/aws/preflight.json`이다. AWS plan/apply, 취약 규칙 주입, 실제 Inspector finding 수집은 수행하지 않았고 클라우드 리소스를 만들지 않았다.

총예산은 180,000원이며, 권한 보완 후 실제 plan·비용을 확인한 별도 생성 승인이 필요하다. `automation/fixtures/*.simulated.json`과 fake AWS client 테스트는 명시적인 모의 자료이며 실제 CVE나 클라우드 증적으로 취급하지 않는다. 인증 성공, 권한 확인, 복구 성공은 서로 다른 검증 단계다.

## 현재 검증 범위

| 대상 | 확인한 내용 | 아직 확인하지 못한 내용 |
| --- | --- | --- |
| SG Lambda | 계정/리전/태그/미부착 SG 제한, IPv4·IPv6 TCP22 정확한 규칙, 중복·권한 오류·검증 실패 처리 | 실제 Config 지연, EventBridge 전달, IAM 성공, SG 복구와 재평가 |
| Inspector Lambda | finding 원본 재조회, approved digest/expiry/scan 확인, project 설정 검증, 영구 dedup·불확실한 시작 차단 | 실제 Inspector finding, 외부 CodeBuild 연결/권한, 빌드 실행 |
| CodeBuild worker | 실제 대상 digest/소유 관계 검사 로직, cosign/scan 실패, 동시 수정, rollout 실패, Pod digest 검증 분기 | 실제 서명/취약점 DB, EKS admission/rollout, 새 digest 실행 |
| 일반 배포 검증 | template뿐 아니라 소유 ReplicaSet/ready Pod runtime digest 검증 로직 | AWS 배포 artifact와 애플리케이션 응답 |

저장소 전체 Python 단위 테스트의 최근 로컬 결과는 **70개 통과**이며 원본은 `evidence/local/unit-tests.txt`에 있다. [GitHub CI run 39116090770](https://github.com/realthoroughbred/capstone_1/actions/runs/39116090770)도 commit `dd13627053f4b76af4ec151894946f5b6509f37f`에서 모든 job이 통과했고, artifact에서 Python 70개·Terraform mock 6개·Checkov 111 passed/0 failed/23 skipped를 확인했다. 증적 디렉터리는 Git에서 제외한다. 자동 복구 관련 테스트는 `tests/test_healing*.py`, `tests/test_inspector*.py`에서 확인할 수 있다. 아래 명령은 AWS 호출 없이 실행된다.

```bash
python -m unittest discover -s tests -v
```

Terraform의 validate/mock plan과 로컬 단위 테스트 통과는 AWS 권한·네트워크·리전 호환성을 증명하지 않는다. ISMS-P 관련 매핑은 구현 통제를 설명하는 자료이며 인증 획득이나 전 항목 준수 판정이 아니다.

### 실제 로컬 GitOps 복구

2026-10-18 09:35 UTC에 `kind-team4`의 Argo CD NetworkPolicy drift 실험은 **PASS**였다. 최초 게시 commit `ba6babcf4b06d340ee79292830cfd1ae576b06b3`의 로컬 Git mirror를 원본으로 사용했다. 실제 정책 변경 승인 → OutOfSync → 허용 client 통신 차단 → 자동 sync operation → 정책·통신 복원을 관측했다. 원본은 `evidence/gitops-kind-team4.json`이다. admission에 거부되어 drift 자체가 없었던 경우를 성공으로 센 결과가 아니다.

`DRIFT_ADMITTED`는 09:35:07.708090, `DRIFT_DETECTED_OUTOFSYNC`는 09:35:08.269252, `AUTOMATIC_RESTORE_VERIFIED`는 09:35:19.297461 UTC였다. timestamp 차이로 drift부터 복원 검증까지 약 **11.589초**이며, JSON의 `elapsed_seconds=4.941`은 복원 대기 구간의 별도 측정값이다. 이 단일 로컬 실험은 AWS Config/Inspector의 지연, EKS 복구 또는 private GitHub 직접 연결을 입증하지 않는다.

## 1. 보안 그룹 복구

실제 경로는 **AWS Config `INCOMING_SSH_DISABLED` → EventBridge → SG Lambda → EC2 재조회/규칙 제거 → 재검증**이다. Config rule과 EventBridge는 전용 demo SG로 범위를 제한한다. 기본값은 `enable_self_healing=false`, 활성화해도 `healing_dry_run=true`이다.

Lambda는 account/region/Config rule/SG allowlist, `Project=team4`, `DemoOnly=true`, SG owner와 **연결된 ENI가 없음**을 확인한다. 각 변경 직전에도 태그와 연결 상태를 다시 확인하며, ingress의 정확한 TCP22 `0.0.0.0/0`·`::/0` 규칙만 rule ID로 제거한다. private CIDR·다른 포트·egress는 건드리지 않는다. all-protocol 또는 SSH를 포함한 넓은 포트 범위는 관련 서비스를 함께 차단하지 않도록 수동 검토로 거부한다.

중복 이벤트는 현재 상태를 다시 조회한다. 이미 없어진 규칙도 실제 재조회로 확인한 뒤에만 처리 완료로 본다. EC2의 ENI 연결 확인과 revoke는 하나의 원자적 트랜잭션이 아니므로 실험 중 다른 주체의 연결·태그 변경을 제한해야 한다. Terraform apply를 동시에 실행하지 않는다.

### 승인된 실제 데모 절차

[AWS 배포 안내](AWS_DEPLOYMENT_GUIDE.md)에 따라 서비스 조회 권한을 먼저 보완하고, 별도 승인을 받아 실제 Config 기록·Lambda를 준비한다. 현재 계정의 기본 조회부터 차단되어 있어 아래 SG preflight도 아직 실행 가능한 상태로 검증되지 않았다. Bash에서 `AWS_PROFILE=team4`를 설정한다. `--approved-demo`가 없으면 규칙을 만들지 않는다.

```bash
export AWS_PROFILE=team4 AWS_REGION=ap-northeast-2 AWS_PAGER=""
DEMO_ACCOUNT=852093844554
test "$(aws sts get-caller-identity --query Account --output text)" = "$DEMO_ACCOUNT"
DEMO_SG="$(terraform -chdir=infra output -raw demo_security_group_id)"
DEMO_FUNCTION="$(terraform -chdir=infra output -raw sg_healing_function_name)"
DEMO_CONFIG_RULE="$(terraform -chdir=infra output -raw config_rule_name)"
python scripts/13-sg-healing-demo.py \
  --account "$DEMO_ACCOUNT" --region ap-northeast-2 --project team4 \
  --security-group-id "$DEMO_SG" --function-name "$DEMO_FUNCTION" \
  --config-rule "$DEMO_CONFIG_RULE" \
  --evidence evidence/aws/sg-healing-preflight.json
```

STS 계정이 승인 계정과 일치하는지 사람이 대조한다. 출력값이 null/빈 값이면 옵션 리소스부터 준비해야 한다. preflight는 정확한 SG/태그/미부착 상태, ACTIVE Config rule, COMPLIANT baseline, Lambda 구성 등을 검사한다. 시험 실행자는 조회 권한과 해당 SG에 한정된 authorize/revoke ingress 권한이 필요하다. IAM 브라우저 세션이 만료되어 cleanup 호출까지 실패하면 수동 정리가 필요하므로, 승인된 실험 시작 전 세션과 권한을 확인한다. 계정 ID를 현재 로그인 결과에서 자동 채택하지 않고 위처럼 지정된 계정과 대조한다.

**명시적인 격리 SG 실험 승인 후**, 검토된 Terraform 변경으로 `healing_dry_run=false`를 적용하고 다음을 실행한다. 아래 옵션은 전체 인프라 삭제 권한을 의미하지 않는다.

```bash
python scripts/13-sg-healing-demo.py \
  --account "$DEMO_ACCOUNT" --region ap-northeast-2 --project team4 \
  --security-group-id "$DEMO_SG" --function-name "$DEMO_FUNCTION" \
  --config-rule "$DEMO_CONFIG_RULE" --approved-demo \
  --timeout-seconds 900 --poll-seconds 10 \
  --evidence evidence/aws/sg-healing-demo.json
```

스크립트는 고유 표시가 있는 world TCP22 규칙 1개를 만들고, 실제 Config NON_COMPLIANT 시각, 동일 rule ID의 Lambda `REMEDIATED` 로그, 규칙 제거, 새로운 COMPLIANT 평가를 모두 기다린다. Lambda를 직접 호출하거나 가짜 이벤트를 전송하지 않는다. 실패/timeout 때 자신이 만든 변경되지 않은 규칙만 정리하고 결과는 **FAIL**로 남긴다. `cleanup=MANUAL_REVIEW_REQUIRED`이면 운영자가 SG와 규칙을 확인해야 하며 성공으로 바꾸지 않는다. 종료 후 승인된 설정 변경으로 dry-run을 복원한다.

### 시간 측정과 증적 판정

| 증적 필드 | 의미 |
| --- | --- |
| `injection_requested_at`, `injection_completed_at` | 실제 주입 API 호출 전후 시각 |
| `config_noncompliant_recorded_at` | 실제 Config NON_COMPLIANT 기록 시각 |
| `lambda_remediation_proof` | 해당 규칙·Config rule·CONFIG_EVENT의 복구 로그 |
| `rule_removal_observed_at`, `config_compliant_recorded_at` | 규칙 제거 관측 및 Config의 후속 COMPLIANT 기록 |
| `injection_to_config_recorded_seconds` | 주입 시작부터 Config 기록까지 |
| `injection_to_removal_observed_seconds` | 주입 시작부터 폴링에서 제거를 관측할 때까지; 기본 10초 폴링 오차 포함 |
| `handler_duration_ms` | Lambda 함수 내부 실행 시간이며 전체 복구 시간과 다름 |

현재 위 실환경 측정값은 **미측정**이다. 1초 이내 탐지/복구 또는 특정 평균 지연을 주장하지 않는다. 결과 JSON의 `status=VERIFIED`, `verification=PASS`와 해당 원본 로그를 함께 검토한다. 모의 fixture의 `SIMULATED_EVENT`를 실제 `CONFIG_EVENT`로 바꿔 보고하지 않는다.

## 2. Inspector 기반 이미지 교체

경로는 **Inspector finding → EventBridge → Lambda 검증/예약 → 기존 trusted CodeBuild → 검증된 digest로 patch → runtime 검증**이다. `enable_inspector_response=false`, `inspector_dry_run=true`가 기본값이다. 실제 존재하는 ACTIVE HIGH/CRITICAL 패키지 finding의 account/region/repository/digest를 Inspector에서 다시 조회하며, 오래되거나 맞지 않는 이벤트는 거부한다.

별도 승인자가 보호된 SSM String에 repository, `approved=true`, 안전한 digest와 24시간 이내 expiry를 등록한다. Lambda/worker는 읽기만 가능하다. 승인 digest가 취약 digest와 같거나, 없거나, 다중 플랫폼 manifest이거나, 스캔 미완료/위험 finding이 있으면 중단한다. worker는 정확한 cosign workflow identity와 issuer를 검증하고 최신 Trivy 스캔에서 unfixed를 포함한 HIGH/CRITICAL을 검사한다.

Lambda는 외부 project의 정확한 source URL·검토된 40자리 commit·buildspec·role·고정 환경·비특권 실행을 확인한다. 실행 시간 15분, 대기 5분으로 제한한다. Terraform은 CodeBuild project와 연결망을 생성하지 않는다. 외부 네트워크, subnet 한정 ENI IAM, private GitHub 연결, KMS artifact 설정은 [automation 계약](automation/README.md)과 [infra-notes](docs/infra-notes.md)를 따라 준비하고 실제로 검증해야 한다.

DynamoDB는 이벤트 ID나 CVE ID 대신 **대상 workload와 취약 digest 조합을 영구 예약**한다. TTL/자동 삭제가 없어 중복 이벤트나 다른 CVE로 재실행을 유도할 수 없다. StartBuild 결과가 불확실하거나 예약 상태와 빌드 기록이 맞지 않으면 자동 재시작하지 않고 수동 검토한다. 재시도가 필요할 때는 DynamoDB·CodeBuild·실제 workload를 먼저 대조하고 승인된 절차로 처리한다.

worker는 취약 digest가 실제 대상에 실행 중인지 확인하고, 승인 재확인 후 현재 resourceVersion·container name·image 조건을 모두 검사하는 JSON patch를 적용한다. Argo CD/Flux가 관리하는 Deployment는 거부한다. rollout 후 template/observed generation/replica count/소유한 ready Pod의 runtime digest를 검사하며, 이전 Pod가 종료 중이면 성공으로 처리하지 않는다. 실패 시 임의의 이전 태그로 rollback하지 않는다. `BUILD_STARTED`는 시작 증거이고, worker의 `VERIFIED`와 증적이 있어야 교체 검증 결과로 사용할 수 있다.

## 3. 실패 처리와 남은 검증

예상 범위를 벗어난 이벤트는 안전하게 거부하고 상태를 기록한다. 재시도 가능한 Lambda 오류는 제한된 재시도 후 SQS 실패 큐/비동기 실패 destination으로 전달된다. CodeBuild 실패 상태도 큐에 보낸다. 큐는 보존 14일이며 CloudWatch queue-depth alarm이 있다. **기본 `notification_topic_arn=""`에서는 사람에게 보내는 alarm action이 없다.** 선택적으로 같은 계정·리전의 승인된 기존 standard SNS topic ARN을 연결할 수 있지만 topic/subscription은 생성하지 않는다. topic/KMS 정책과 확정된 수신자를 준비하고 실제 전달을 검증해야 알림 완료라고 기록할 수 있다. 현재 AWS 알림은 실행 검증하지 않았다. 운영자는 기본 상태에서 큐/로그를 확인해야 하며 모든 거부 이벤트가 DLQ에 들어가는 것은 아니다.

로그·증적은 필요한 ID/상태/시각만 기록하며 raw event, secret 값, 인증 token, 외부 명령의 민감 출력은 남기지 않는다. S3 증적·CodeBuild artifact·배포 runtime JSON을 함께 보존한다. 남은 실환경 검증은 IAM 권한 보완 → 리소스 inventory 및 실제 plan → 180,000원 예산 내 비용·생성 승인 → apply → controller/배포 검증 → 별도 SG 실험 승인 → Config 복구 측정 → 실제 Inspector 및 승인 replacement로 worker 검증 순서이다. 리소스 삭제는 [COST_AND_CLEANUP](COST_AND_CLEANUP.md)의 새로운 명시적 승인 절차를 따른다.
