# Infrastructure implementation notes

These are implementation and operating constraints, not proof of a live deployment. No AWS resources were created or changed by this work. A real account-specific plan, paid-resource approval and AWS integration tests remain required.

## Baseline and version choices

- Uses one managed EKS node (`t3.large`, AL2023, encrypted gp3), two public subnets, no NAT Gateway and no ALB. Worker public IPv4 permits outbound image/tool downloads through the Internet Gateway. There is no SSH access, NodePort or public load balancer in the supplied workload. Production should reconsider private nodes and redundant capacity.
- The full add-on set may exceed the standard VPC-CNI 17-Pod capacity of the previous `t3.medium`. The new `t3.large` default has 8 GiB and a standard 35-Pod ceiling; this is a planning capacity estimate, not a scheduling test. Size/count are explicit variables (minimum/desired 1, maximum 2). A maximum of 2 is a scaling bound, not two continuously running nodes, and no autoscaler is installed. The larger instance increases hourly EC2 cost; review the regional quote before approval. See [EKS node instance selection](https://docs.aws.amazon.com/eks/latest/userguide/choosing-instance-type.html).
- EKS API access is private for workers and public only for validated operator IPv4 `/32` addresses. GitHub deploy therefore requires a trusted runner with an allowed stable egress address or private API routing. A standard GitHub-hosted runner is not implicitly allowed.
- Terraform CLI constraint is `>=1.10,<2`; verified local CLI is 1.12.2. `.terraform.lock.hcl` records AWS 6.65.0 and archive 2.8.1, installed from signed HashiCorp packages. No third-party Terraform module is used. Retain the lock file in Git; review provider upgrades before `init -upgrade`.
- Kubernetes 1.35 remains in standard EKS support on the user's 2026-10-18 reference date. Regional availability and add-on versions must still be queried immediately before deployment. `scripts/05-addon-versions.sh` supplies the regional add-on versions. The fixture values in `infra/tests` are synthetic and must not be used for deployment. See [EKS version lifecycle](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html) and [AWS provider versioning](https://developer.hashicorp.com/terraform/tutorials/configuration-language/configure-providers).
- VPC CNI network policy support is enabled; local Calico is not installed into EKS. Consult [VPC CNI network policy requirements](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html) for the selected version and run actual allow/deny tests after deployment.
- Lambda uses Python 3.12 on AL2023; [AWS's runtime table](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html) currently lists support through October 2028. The archive includes the reviewed `automation/` sources; no secret values are packaged.

## Access and encryption

The account ID is mandatory and enforced by the AWS provider. Explicit operator IAM principals receive initial cluster administration; automatic creator administrator access is disabled. Workload automation uses separate identities:

For the authenticated team4 account, [the IAM setup guide](TEAM4_IAM_PERMISSIONS.md) supplies separate metadata, provisioning, runtime-boundary and optional validation policies. These deliberately require administrator-reviewed bootstrap for the exact new default SG, KMS key, EKS OIDC issuer and network resource IDs. The base runtime boundary excludes regional ENI mutations; the separate CNI fragment is a template restricted to the CNI role and approved VPC/subnets. A successful Terraform plan or mock test does not prove these IAM prerequisites are satisfied. Do not run a full apply until the administrator has reviewed those exact-resource additions and the paid plan is approved.

| Identity | Boundary |
|---|---|
| Node instance profile | Worker-node and ECR-pull policies; IMDSv2 required, hop limit 1 |
| `kube-system/aws-node` IRSA | VPC CNI policy, removed from the node profile; add-on installed before node creation |
| `demo/eso-secrets-reader` IRSA | Read the one demo secret; KMS decrypt restricted to Secrets Manager and the secret encryption context |
| `kyverno/kyverno-admission-controller` IRSA | ECR auth token plus read operations on the one repository |
| GitHub OIDC role | Exact repository/environment subject and STS audience; push to one ECR repository and describe one cluster; EKS group `team4:deploy` |
| SG Lambda | Describe resources; revoke ingress on the one demo SG with matching Project/DemoOnly tags |
| Inspector Lambda | Read findings/scan/approval; reserve state; start only the named reviewed CodeBuild project |
| CodeBuild worker | Read approval/image; inspect/patch the demo workload through group `team4:image-remediator`; update existing remediation state; no approval write |

Apply the Kubernetes RoleBindings from `k8s/` as the bootstrap operator; EKS access entries alone do not grant Kubernetes API permissions. Protect the GitHub environment with required reviewers and main-only deployment rules. Reuse an existing GitHub OIDC provider through `existing_github_oidc_provider_arn`; do not create a second provider for the same issuer. IAM can retrieve OIDC certificate thumbprints when omitted, per [AWS's OIDC provider update](https://aws.amazon.com/about-aws/whats-new/2024/07/aws-identity-access-management-open-id-connect-identity-providers/).

The authenticated repository API returned `use_immutable_subject:true` and `sub_claim_prefix:repo:realthoroughbred@272421931/capstone_1@1378935906`. Terraform uses that exact prefix followed by `:environment:aws-demo`; it does not accept a legacy subject fallback. For a fork, query that repository's OIDC customization endpoint and update both `github_repository` and `github_subject_prefix`. [GitHub's AWS OIDC documentation](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) explains immutable subject IDs and environment trust.

One rotating customer-managed KMS key encrypts EKS secrets, ECR, Secrets Manager, CloudWatch, optional evidence and deduplication storage. This adds a key charge and request charges; it is a deliberate shared-key lab compromise. All five EKS control-plane log types and VPC Flow Logs are enabled with one-year retention. The VPC default SG has no rules. The Secrets Manager resource deliberately has no Terraform-managed secret version: insert a non-production JSON value with property `token` through the approved bootstrap workflow so it is absent from Terraform state.

Application ECR tags are immutable. The only mutability exclusions are `sha256-*.sig` and `sha256-*.att`, the Cosign v2 signature and attestation artifact tags which must be updated when appending a signature/attestation to an existing digest. No application tag may use those reserved patterns; workloads still deploy by digest and require signature verification. The mock plan asserts the exact two exclusions. See [ECR tag mutability exclusions](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-tag-mutability.html) and the [AWS provider's exclusion schema](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/ecr_repository.html.markdown).

## Config remediation

`enable_self_healing=false` is the default. Before enabling, inspect the existing regional Config recorder and delivery channel:

```sh
aws configservice describe-configuration-recorders --region ap-northeast-2
aws configservice describe-configuration-recorder-status --region ap-northeast-2
aws configservice describe-delivery-channels --region ap-northeast-2
```

If a running recorder already includes `AWS::EC2::SecurityGroup`, supply `existing_config_recorder_name` and leave `create_config_recorder=false`. The supplied name is a deliberate acknowledgement; the operator must inspect its running status and recorded types. In a dedicated account without a recorder, explicitly set `create_config_recorder=true`; the created recorder records only SecurityGroup configuration, continuously. Do not overwrite an organization's recorder or delivery channel.

The managed rule named `${project}-restricted-ssh` uses AWS identifier `INCOMING_SSH_DISABLED`; these strings differ by AWS design. Its scope is the exact unattached demo security group. EventBridge also filters account, region, rule, resource and NON_COMPLIANT status. See [restricted-ssh](https://docs.aws.amazon.com/config/latest/developerguide/restricted-ssh.html).

`healing_dry_run=true` remains the default even when resources are enabled. After separate approval for the controlled experiment, set it false using a reviewed plan. Before each mutation the handler revalidates account, project, demo tag, allowlisted SG ID and absence of network interfaces. IAM cannot express “unattached,” so that check is enforced in code in addition to the exact-resource IAM boundary. The experiment must never attach this SG to a workload.

Terraform's canonical SG has zero ingress and egress. The experiment temporarily adds an external SSH rule outside Terraform, and the handler returns it to that canonical state. No `ignore_changes` hides ingress drift. Do not run Terraform apply concurrently with the experiment. Capture the before-state, mutation time, Config evaluation event time, Lambda result and final rule query; handler execution duration is not end-to-end Config detection latency. Repeated NON_COMPLIANT delivery is safe because absent rules produce no mutation.

Evidence is versioned and encrypted; Config delivery uses its own `config/` prefix. Resource policies enforce same-account service delivery and HTTPS. The Config service and recorder have the documented delivery permissions described in [Config S3 permissions](https://docs.aws.amazon.com/config/latest/developerguide/s3-bucket-policy.html) and [Config KMS permissions](https://docs.aws.amazon.com/config/latest/developerguide/s3-kms-key-policy.html).

## Inspector response and the external worker

`enable_inspector_response=false` is the default. Enabling it changes the account/region ECR registry scanning configuration to enhanced continuous scanning for the demo repository. Inspect and preserve any existing registry configuration first; this stack must not replace existing organizational scanning settings. Registry configuration is a singleton; use a dedicated account or explicitly merge reviewed existing rules before applying.

No CodeBuild project, NAT or proxy is created. Supply a dedicated existing `remediation_codebuild_project_name` and a reviewed 40-character `remediation_source_revision`. Configure the project using `terraform output -json remediation_codebuild_contract`: exact source URL and revision, supplied buildspec, fixed environment, supplied service role, nonprivileged build, and CloudWatch log group. Use a suitable Linux environment with Python/AWS CLI; the buildspec installs pinned security tools. The project must not accept unreviewed pull-request builds with the remediation role. Runtime roles have no permission to modify the project or the approval parameter.

Set the external project's S3 artifacts to the exported bucket, `inspector` path, `BUILD_ID` namespace and enabled encryption. The buildspec uploads `evidence/inspector-remediation.json`; the worker's exit status still determines build success. The role can write only this prefix and cannot delete evidence. Lambda also records results directly to its own prefix.

The existing repository is private. Configure the external project's authorized source connection before enabling response; the runtime role cannot manufacture repository credentials. If using CodeConnections, its administrator must grant `codeconnections:UseConnection` only for the exact approved connection. Use the exported `encryption_key` for build artifacts; do not silently substitute an unrelated key.

The project must reach both the restricted EKS API and public dependencies (GitHub releases, signatures and vulnerability databases). Standard hosted CodeBuild has dynamic public egress. A VPC build in a public subnet has no public IPv4 and cannot use the Internet Gateway directly; [AWS requires NAT or an appropriate proxy](https://docs.aws.amazon.com/codebuild/latest/userguide/vpc-support.html) for public dependency access. Suitable externally approved options are:

1. A dedicated CodeBuild VPC with fixed NAT/proxy egress; allow its exact fixed IPv4 `/32` in the EKS endpoint CIDRs.
2. An existing routed private build network with approved EKS connectivity and outbound NAT/proxy; review cluster security-group ingress and attach an administrator-reviewed EC2 ENI policy scoped to its build subnets.

The generated role intentionally omits broad EC2 network-interface permissions because this stack does not know or own the external build network. The network administrator must bind a separate least-privilege ENI policy to the exported role when a VPC build requires it. This is a deployment prerequisite, not a claim that connectivity was verified.

Create the protected SSM **String** approval parameter outside the automation roles. Its JSON contains the repository name, exact `sha256:` digest, `approved:true` and a future `expires_at` timestamp. Neither Lambda nor the worker may change approval. Keep `inspector_dry_run=true` until the replacement experiment is approved; keep the external project's fixed DRY_RUN value identical. A safe digest must pass current scan and trusted signature checks before replacement; without a safe digest the response stops.

Deduplication rows have no TTL and no runtime delete permission, preventing old events from becoming newly eligible. Uncertain build-start outcomes require manual review. Lambda failure destinations and CodeBuild FAILED/FAULT/STOPPED/TIMED_OUT events go to the encrypted SQS failure queue; the CloudWatch queue-depth alarm provides a visible failure state. Set optional `notification_topic_arn` to an existing approved standard SNS topic in the same account and region to notify its subscribers on an ALARM transition. Empty is the default: it is a metric-only alarm with **no human notification**. This stack creates no topic or subscriptions and does not send test messages. The topic owner must allow `cloudwatch.amazonaws.com` to publish with the specific alarm `aws:SourceArn` and target `aws:SourceAccount`, confirm subscriptions, and authorize the encryption key when applicable; see [AWS CloudWatch alarm notifications](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Notify_Users_Alarm_Changes.html). Delivery requires separate approved live verification. Simulated EventBridge payloads and genuine Inspector findings must be labelled separately in evidence.

## Checkov exceptions and review scope

Suppressions are resource-local with explanations. They do not claim production compliance:

| Check | Reason and compensating boundary |
|---|---|
| `CKV_AWS_130` | Public worker subnets preserve the no-NAT lab budget; no unsolicited node ingress is configured |
| `CKV_AWS_39` | Public EKS endpoint is needed by an approved operator/runner and is limited to validated IPv4 `/32`; private access is enabled |
| `CKV_AWS_38` | Static scan has no value for the required CIDR input; Terraform validation enforces `/32`, and a negative mock test rejects `0.0.0.0/0`; inspect the real plan's resolved CIDRs |
| `CKV_AWS_51` | Checkov 3.3.29 accepts only literal `IMMUTABLE`; exact `.sig`/`.att` artifact exclusions are required by Cosign v2 and tested; workload tags remain immutable |
| `CKV_AWS_355` | Selected Describe/List/GetAuthorizationToken/caller-identity APIs cannot be resource-scoped; all supported mutation/read resources are scoped |
| `CKV2_AWS_57` | A synthetic test token is rotated manually to verify ESO; no production secret rotation claim |
| `CKV_AWS_117` | API-only Lambda stays outside the VPC to avoid NAT/endpoints and has no workload-network access |
| `CKV_AWS_272` | AWS Signer is not provisioned; source is reviewed and the archive hash is tracked; production signing remains a separate task |
| `CKV_AWS_27` | Failure queue uses SQS-managed server-side encryption for non-secret event envelopes |
| `CKV_AWS_144` | Evidence is versioned and retained in one region; cross-region replication adds cost outside the lab scope |
| `CKV_AWS_18` | Evidence bucket has no separate access-log bucket; execution records are in CloudWatch; add an organizational access-log destination for production |
| `CKV2_AWS_62` | Evidence is explicitly exported/read; no S3 event consumer is required |
| `CKV2_AWS_5` | The experiment security group is intentionally unattached; attaching it would violate the remediation guard |
| `CKV2_AWS_45`, `CKV2_AWS_48` | Continuous recording covers the experiment's SecurityGroup type only to bound scope/cost; existing organizational recorders are not replaced |

Further static findings must be fixed or documented at their resource before the CI gate is declared passing. Local `terraform validate` checks configuration/schema; mock `terraform test` checks safe-default branches and rejected missing prerequisites. Neither command replaces an authenticated plan or AWS integration test.

Run mock tests through `bash infra/test-isolated.sh` after provider initialization, or use `bash infra/validate-local.sh` for the full local checks. Terraform tests normally inherit automatic variable files; real deployment settings can therefore change a test intended to verify module defaults. The wrapper copies tracked Terraform configuration, the lockfile, test definitions and three allowlisted Lambda source files into a temporary directory. It excludes deployment variable files, state, plans, credentials and backend metadata, and clears test-variable/CLI environment overrides in its own process. It reuses installed provider executables and removes only its temporary directory afterward. Add new Terraform/test source files to Git before running this wrapper so they are included. User deployment files remain in place. See [HashiCorp test variable precedence](https://developer.hashicorp.com/terraform/language/tests#variable-definition-precedence).

## Cost and cleanup boundaries

The 2026-10-23 live run exposed two provider/runtime requirements absent from mock tests. The node launch template now explicitly selects the new cluster security group, so EKS's launch authorization check does not fall back to the closed VPC default security group. This does not open the default group or add a node.

AWS rejected reserved Lambda concurrency 1 because it would reduce the shared unreserved pool below the account's minimum of 10. The module still defaults to a per-function reservation of 1. For this short-lived SG experiment only, the ignored deployment inputs explicitly set `healing_use_unreserved_concurrency_for_demo=true`. That uses shared account concurrency and **does not enforce a per-function cap**. The one-SG allowlist, default dry-run, 60-second timeout, two retries, failure queue, original budget and cleanup deadline remain in place. Do not carry this exception into production or claim that passing a static scan proves a runtime concurrency cap. Request an appropriate Lambda concurrency quota before restoring reserved concurrency. [AWS concurrency behavior](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html), [provider setting](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function).

Live EC2 queries also returned empty filtered ENI pages with continuation tokens. The SG guard now follows every page, rejects any attachment, and fails closed on repeated tokens or a 20-page limit. Empty first pages are neither proof of attachment nor proof of absence. The same guard runs before the test and again before remediation.

The live SG test reads evaluations through `GetComplianceDetailsByConfigRule`, which the operator can use on the project's tagged rule. It filters every page by exact rule name, resource type and SG ID. It does not need account-wide resource compliance read permission, and refuses injection until Config has recorded a compliant baseline. A passing preflight is not proof that real EventBridge/Lambda remediation has occurred.

The live Config recorder reported `AccessDenied` for EC2 resource recording with its original three Describe actions. Its service role now uses the `ec2:Describe*` read family present in [AWS_ConfigRole](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AWS_ConfigRole.html), limited to the configured region. Recording remains limited to SecurityGroup and the compliance rule to the single demo SG. CloudTrail diagnostics confirmed denied relationship Describe calls before the change and successful recording afterward. This scope grants EC2 metadata reads, without EC2 mutations or additional operator privileges.

The recorded SG still had no compliance result. `DescribeConfigRuleEvaluationStatus` and CloudTrail identified an explicit `config:PutEvaluations` denial for `team4-config-recorder/configLambdaExecution`. The Config role policy now permits this single result-submission API in the configured region. The administrator-owned runtime boundary needs the matching allowance, restricted by both `aws:PrincipalArn` to the Config role and `aws:RequestedRegion` to Seoul. Existing CNI statements must be preserved when updating that boundary. This allows the service to submit its genuine evaluations; the operator does not call PutEvaluations or fabricate test results. The endpoint accepts rule evaluation results as described in [PutEvaluations](https://docs.aws.amazon.com/config/latest/APIReference/API_PutEvaluations.html). Applied code alone does not prove live remediation; require a compliant baseline and the full Config/EventBridge/Lambda experiment evidence.

Baseline billable items include EKS control plane, EC2, EBS, public IPv4, KMS, Secrets Manager and CloudWatch ingestion/storage. Optional components add Config recording/evaluation, S3, Lambda, EventBridge, SQS, DynamoDB/PITR and Inspector scanning. Externally supplied CodeBuild and its network have separate charges. No deployment or cleanup runs without the user's requested cost/impact approval.

The evidence bucket has `force_destroy=false` and one-year lifecycle retention; ECR has `force_delete=false`; Secrets Manager uses seven-day recovery; the KMS key schedules deletion only after 30 days. A successful destroy plan does not mean stored evidence/images may be silently deleted. Export required evidence first, review resource ownership and retain or remove it with explicit authorization. Preserve state securely outside Git. A budget alarm is a notification, not automatic shutdown.
