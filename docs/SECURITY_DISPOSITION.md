# 생략·실패·취약점 처리 검토표

기준: 2026-11-16. 분류는 검사 결과·종료 코드·배포 기준을 바꾸지 않는다. REVIEWED_EXCEPTION은 기술적 사유를 검토했다는 뜻이며 이번 실행의 승인으로 간주하지 않는다. 담당자는 원본 WBS를 유지하고 손초애의 통제 검토와 관련 구현 담당의 판단을 함께 받는다.

이번 Checkov는 **184통과·3실패·23생략**이다. 과거 CI 111/0/23 및 과거 로컬 164/0/23과 별개다. 새 시험용 S3의 접근 로그·교차 리전 복제·이벤트 알림 3개는 조치가 남았다. 기존 정책의 생략을 늘리거나 gate를 약화하지 않았다.

| 도구/ID | 대상 | 상태 | 원래 사유 또는 다음 조치 |
|---|---|---|---|
| checkov/CKV_AWS_355 | aws_iam_role_policy.github_deploy[0] | 기술 검토된 예외 후보(미승인) | GetAuthorizationToken has no resource-level permission; all image operations are scoped to the demo repository. |
| checkov/CKV_AWS_355 | aws_iam_role_policy.config[0] | 기술 검토된 예외 후보(미승인) | Config uses EC2 Describe APIs for resource relationships and PutEvaluations for rule results. These APIs use wildcard resources; region is constrained and recording remains SecurityGroup-only. No EC2 write is granted. |
| checkov/CKV_AWS_27 | aws_sqs_queue.failures[0] | 기술 검토된 예외 후보(미승인) | SQS-managed SSE encrypts non-secret failure event envelopes; no customer-managed queue key is needed for this lab. |
| checkov/CKV_AWS_355 | aws_iam_role_policy.healing[0] | 기술 검토된 예외 후보(미승인) | EC2 Describe and STS caller identity do not support resource-level IAM. Mutation is restricted to one tagged unattached demo SG. |
| checkov/CKV_AWS_272 | aws_lambda_function.healing[0] | 조치 필요 | Lambda code signing requires separately approved AWS Signer infrastructure; archive source hash tracks reviewed code. |
| checkov/CKV_AWS_117 | aws_lambda_function.healing[0] | 기술 검토된 예외 후보(미승인) | API-only Lambda needs no private network access; VPC attachment would require NAT or billed endpoints. |
| checkov/CKV_AWS_355 | aws_iam_role_policy.remediation | 기술 검토된 예외 후보(미승인) | GetAuthorizationToken and GetCallerIdentity require wildcard resources; cluster, repository, approval and state writes are narrowly scoped. |
| checkov/CKV_AWS_355 | aws_iam_role_policy.inspector | 기술 검토된 예외 후보(미승인) | Inspector ListFindings and STS GetCallerIdentity require wildcard resources; code verifies account, repository, severity and finding digest. |
| checkov/CKV_AWS_272 | aws_lambda_function.inspector | 조치 필요 | Code signing requires separately approved AWS Signer infrastructure; source archive hash tracks reviewed code. |
| checkov/CKV_AWS_117 | aws_lambda_function.inspector | 기술 검토된 예외 후보(미승인) | API-only Lambda needs no VPC access; the external CodeBuild project has separately approved cluster connectivity. |
| checkov/CKV_AWS_130 | aws_subnet.public[0] | 기술 검토된 예외 후보(미승인) | Approved demo design uses public node IPv4 without NAT; no inbound node ports are exposed. |
| checkov/CKV_AWS_39 | aws_eks_cluster.demo | 기술 검토된 예외 후보(미승인) | Public endpoint is restricted to validated operator IPv4 /32s; private access remains enabled for nodes. |
| checkov/CKV_AWS_38 | aws_eks_cluster.demo | 미해결 | Static scan cannot resolve the required operator CIDR input; validation requires every entry to be IPv4 /32 and mock tests reject 0.0.0.0/0. |
| checkov/CKV_AWS_51 | aws_ecr_repository.test | 기술 검토된 예외 후보(미승인) | Only Cosign sha256-*.sig/.att artifact tags are mutable; application tags remain immutable and deployments use signed digests. Checkov 3.3.29 only accepts literal IMMUTABLE. |
| checkov/CKV_AWS_130 | aws_subnet.public[1] | 기술 검토된 예외 후보(미승인) | Approved demo design uses public node IPv4 without NAT; no inbound node ports are exposed. |
| checkov/CKV_AWS_355 | aws_iam_role_policy.kyverno | 기술 검토된 예외 후보(미승인) | ECR GetAuthorizationToken does not support resource-level permissions; image reads are scoped to one repository. |
| checkov/CKV2_AWS_45 | aws_config_configuration_recorder_status.demo[0] | 기술 검토된 예외 후보(미승인) | Recorder is enabled continuously for SecurityGroup only, the explicit experiment scope; this is not an account-wide compliance baseline. |
| checkov/CKV2_AWS_48 | aws_config_configuration_recorder.demo[0] | 기술 검토된 예외 후보(미승인) | Dedicated lab recorder intentionally records SecurityGroup only to bound evaluation scope and charges; existing organization recorders are preserved. |
| checkov/CKV2_AWS_62 | aws_s3_bucket.evidence[0] | 기술 검토된 예외 후보(미승인) | Evidence is consumed explicitly by report/export commands; no event consumer is required. |
| checkov/CKV2_AWS_57 | aws_secretsmanager_secret.demo | 기술 검토된 예외 후보(미승인) | Demo token rotation is manually verified through ESO; no production credential or rotation Lambda is created. |
| checkov/CKV2_AWS_5 | aws_security_group.healing_demo | 기술 검토된 예외 후보(미승인) | This security group must remain unattached for the explicitly bounded remediation experiment. |
| checkov/CKV_AWS_144 | aws_s3_bucket.evidence[0] | 미해결 | Dedicated regional lab evidence uses versioning and retention; cross-region replication adds unapproved cost. |
| checkov/CKV_AWS_18 | aws_s3_bucket.evidence[0] | 조치 필요 | No sensitive workload data is stored; bucket delivery and Lambda execution are audited in CloudWatch. Add an organization access-log sink before production. |
| checkov/CKV2_AWS_62 | aws_s3_bucket.sandbox | 조치 필요 | Ensure S3 buckets should have event notifications enabled |
| checkov/CKV_AWS_144 | aws_s3_bucket.sandbox | 조치 필요 | Ensure that S3 bucket has cross-region replication enabled |
| checkov/CKV_AWS_18 | aws_s3_bucket.sandbox | 조치 필요 | Ensure the S3 bucket has access logging enabled |
| trivy/CVE-2026-107891 | musl | 조치 필요 | Old digest remains blocked; replacement passed local scan but requires separate AWS publish/sign/approval. |
| trivy/CVE-2026-107891 | musl-utils | 조치 필요 | Old digest remains blocked; replacement passed local scan but requires separate AWS publish/sign/approval. |
| trivy/CVE-2026-85091 | zlib | 조치 필요 | Old digest remains blocked; replacement passed local scan but requires separate AWS publish/sign/approval. |
| trivy/CVE-2026-4738 | zlib | 조치 필요 | Old digest remains blocked; replacement passed local scan but requires separate AWS publish/sign/approval. |

새 Lambda의 일부 AWS 서명/VPC/DLQ 통제와 S3 관련 서비스 권한·실제 정책은 정적 도구가 자동으로 모든 위험을 찾는다고 가정하지 않는다. 실제 AWS 실행 전에 IAM 경계·로그 전달·실패 queue를 검증한다.

이미지 최초 결과는 HIGH 3건·MEDIUM 1건이었다. 수정한 로컬 이미지에서는 발견 항목 0건, package 17개가 확인됐다. 옛 digest를 안전으로 바꾸지 않았으며 새 이미지는 아직 AWS 승인 이미지가 아니다. 원본: [최초 Trivy](../evidence/finalization-20261116/candidate-image/trivy.json), [수정 후 Trivy](../evidence/finalization-20261116/fixed-image/trivy.json).

[기계 판독 처리표](../policies/exception-register.json), [실습서의 점수·gate 설명](LAB_BOOK.md#5-검사이미지sbom보고서).
