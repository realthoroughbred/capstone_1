# Self-Healing 구현 및 검증 보고서

**2026-10-23 실환경 결과:** Config→EventBridge→Lambda 보안 그룹 자동복구와 EKS Argo CD 정책 복구를 실제 AWS에서 검증했다. ECR 서명·SBOM·EKS 배포, NetworkPolicy, ESO rotation, Kyverno 미서명 이미지 거부도 통과했다. 이번 실험에서 생성한 Terraform 자원은 67개이며 검증 후 정리 상태는 [현재 상태](IMPLEMENTATION_STATUS.md)를 따른다.

SG 시험은 ENI에 연결하지 않은 `DemoOnly=true` 그룹에 TCP22 공개 규칙 하나를 주입했다. 실제 Config 평가와 Lambda 로그, 최종 EC2 규칙 조회를 대조했으며 수동 Lambda 호출이나 모의 Config 이벤트는 사용하지 않았다. `evidence/aws/sg-healing-demo.json`은 `VERIFIED/PASS`다. **Inspector finding에 따른 이미지 자동 교체는 이번 승인 계획에 포함되지 않아 실검증하지 않았다.** 일반 서명 이미지 배포 성공을 Inspector 자동교체 성공으로 계산하지 않는다.

총예산은 180,000원이며 신규 생성·최대 8시간 검증·DemoOnly SG 시험·검증 후 신규 자원 정리가 승인됐다. Config 기록 역할의 EC2 조회 범위와 `PutEvaluations` 누락을 실제 오류로 진단해 보완한 뒤 시험했다. 운영자 권한 경계는 관리자가 수정했다. `automation/fixtures/*.simulated.json`과 fake AWS client 테스트는 모의 자료로 유지한다.

| SG 시험 단계 | UTC 시각 / 측정값 |
| --- | --- |
| 규칙 주입 요청 | 2026-10-23 13:46:28.798 |
| Config NON_COMPLIANT 결과 기록 | 13:48:04.508 · 주입 요청부터 **95.710초** |
| Lambda 규칙 제거 후 검증 | handler **1,343ms** · 실제 Config 이벤트에서 실행 |
| 외부 조회에서 규칙 제거 관측 | 13:48:32.271 · 주입 요청부터 **123.473초** |
| Config COMPLIANT 재평가 | 13:49:58.947 |
| 전체 증거 검증 종료 | 13:50:07.012 |

제거 관측 시간에는 API 조회·polling 지연이 포함된다. handler 처리 시간은 Config 탐지 지연과 다르다. 시험 후 Lambda는 dry-run으로 복원했고, 새 EventBridge rule·Config recorder를 중지했다. 실패 큐의 visible/in-flight/delayed 메시지는 모두 0개였다.

## 현재 검증 범위

| 대상 | 확인한 내용 | 아직 확인하지 못한 내용 |
| --- | --- | --- |
| SG Lambda | 실제 IPv4 TCP22 주입→Config→EventBridge→Lambda 제거→정상 재평가, 범위·오류 처리 단위 테스트 | IPv6 위반 주입과 장기 반복 부하 시험 |
| Inspector Lambda | finding 원본 재조회, approved digest/expiry/scan 확인, project 설정 검증, 영구 dedup·불확실한 시작 차단 | 실제 Inspector finding, 외부 CodeBuild 연결/권한, 빌드 실행 |
| CodeBuild worker | 실제 대상 digest/소유 관계 검사 로직, cosign/scan 실패, 동시 수정, rollout 실패, Pod digest 검증 분기 | 실제 서명/취약점 DB, EKS admission/rollout, 새 digest 실행 |
| 일반 배포 검증 | 실제 GitHub OIDC·ECR 서명·SBOM과 소유 ReplicaSet/Ready Pod runtime digest·HTTP 응답 | Inspector 경로의 이미지 교체와 혼동하지 않음 |

저장소 전체 Python 단위 테스트는 2026-10-23 로컬 재검증에서 **106개 통과**, Terraform mock **9개 통과**, Checkov **164 passed / 0 failed / 23 documented skips**였다. 원본은 `evidence/local/unit-tests.txt`, `evidence/terraform/`에 있다. Config 결과 제출을 특정 역할·리전으로 제한하는 회귀 검사도 포함한다. 증적 디렉터리는 Git에서 제외한다. 아래 명령은 AWS 호출 없이 실행된다.

실제 배포에 사용한 main commit의 [CI run 39955517961](https://github.com/realthoroughbred/capstone_1/actions/runs/39955517961)과 [AWS 배포 run 39955813458](https://github.com/realthoroughbred/capstone_1/actions/runs/39955813458)은 모두 성공했다. 이후 Config 권한 보완·보고서 변경의 CI는 해당 변경 commit 결과를 별도로 확인한다.

```bash
python -m unittest discover -s tests -v
```

Terraform의 validate/mock plan과 로컬 단위 테스트 통과는 AWS 권한·네트워크·리전 호환성을 증명하지 않는다. ISMS-P 관련 매핑은 구현 통제를 설명하는 자료이며 인증 획득이나 전 항목 준수 판정이 아니다.

### 실제 EKS 및 로컬 GitOps 복구

EKS에서는 main commit `a2288bd2db999decc04ea365669d5d791d8f34eb`의 읽기 전용 클러스터 내부 Git 미러를 사용했다. 2026-10-23 13:24:06.864 UTC에 NetworkPolicy drift를 허용한 뒤 OutOfSync와 실제 통신 차단, Argo CD 자동 sync, 정책·통신 복원을 관측했다. 복원 검증 시각은 13:24:31.077 UTC로 주입부터 약 **24.213초**다. 원본은 `evidence/gitops-team4-eks.json`이며 private GitHub 직접 인증 연동은 미검증이다.

2026-10-18 09:35 UTC에 `kind-team4`의 Argo CD NetworkPolicy drift 실험은 **PASS**였다. 최초 게시 commit `ba6babcf4b06d340ee79292830cfd1ae576b06b3`의 로컬 Git mirror를 원본으로 사용했다. 실제 정책 변경 승인 → OutOfSync → 허용 client 통신 차단 → 자동 sync operation → 정책·통신 복원을 관측했다. 원본은 `evidence/gitops-kind-team4.json`이다. admission에 거부되어 drift 자체가 없었던 경우를 성공으로 센 결과가 아니다.

`DRIFT_ADMITTED`는 09:35:07.708090, `DRIFT_DETECTED_OUTOFSYNC`는 09:35:08.269252, `AUTOMATIC_RESTORE_VERIFIED`는 09:35:19.297461 UTC였다. timestamp 차이로 drift부터 복원 검증까지 약 **11.589초**이며, JSON의 `elapsed_seconds=4.941`은 복원 대기 구간의 별도 측정값이다. 이 단일 로컬 실험은 AWS Config/Inspector의 지연, EKS 복구 또는 private GitHub 직접 연결을 입증하지 않는다.

## 1. 보안 그룹 복구

실제 경로는 **AWS Config `INCOMING_SSH_DISABLED` → EventBridge → SG Lambda → EC2 재조회/규칙 제거 → 재검증**이다. Config rule과 EventBridge는 전용 demo SG로 범위를 제한한다. 기본값은 `enable_self_healing=false`, 활성화해도 `healing_dry_run=true`이다.

Lambda는 account/region/Config rule/SG allowlist, `Project=team4`, `DemoOnly=true`, SG owner와 **연결된 ENI가 없음**을 확인한다. 각 변경 직전에도 태그와 연결 상태를 다시 확인하며, ingress의 정확한 TCP22 `0.0.0.0/0`·`::/0` 규칙만 rule ID로 제거한다. private CIDR·다른 포트·egress는 건드리지 않는다. all-protocol 또는 SSH를 포함한 넓은 포트 범위는 관련 서비스를 함께 차단하지 않도록 수동 검토로 거부한다.

중복 이벤트는 현재 상태를 다시 조회한다. 이미 없어진 규칙도 실제 재조회로 확인한 뒤에만 처리 완료로 본다. EC2의 ENI 연결 확인과 revoke는 하나의 원자적 트랜잭션이 아니므로 실험 중 다른 주체의 연결·태그 변경을 제한해야 한다. Terraform apply를 동시에 실행하지 않는다.

### 승인된 실제 데모 절차

[AWS 배포 안내](AWS_DEPLOYMENT_GUIDE.md)에 따라 실제 plan·비용과 실험 범위를 검토한다. 이번 시험은 기존 명시적 승인에 따라 실행했으며 아래는 재현 절차다. 정리 후 다시 시험하려면 새 자원과 정상 Config baseline부터 준비한다. Bash에서 `AWS_PROFILE=team4`를 설정한다. `--approved-demo`가 없으면 규칙을 만들지 않는다.

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

자동복구 증적은 필요한 ID/상태/시각을 기록하며 secret 값·인증 token을 포함하지 않는다. S3 증적·배포 runtime JSON·ECR OCI blob과 운영 로그 백업을 Git에서 제외한 로컬에 보존한다. 승인된 실검증은 통과했으며 최종 신규 자원 정리 상태는 [COST_AND_CLEANUP](COST_AND_CLEANUP.md)과 실제 삭제 후 조회 증거를 따른다. Inspector/외부 CodeBuild 확장은 별도 범위로 남긴다.
