# Guarded remediation

This directory implements AWS handlers and a CodeBuild worker. Local fake-client tests pass independently of AWS credentials. **No real Config detection, Inspector finding, EKS replacement, or cloud remediation is established by those tests.** JSON files under `fixtures/` are explicitly simulated, use example account IDs and fabricated digests, and are never evidence of a real CVE.

## Security group handler

Package the contents of this directory at the Lambda ZIP root; handler: `sg_healing.lambda_handler`. The Python Lambda runtime supplies boto3. Terraform owns packaging and IAM.

Required environment: `EXPECTED_ACCOUNT_ID`, `EXPECTED_REGION`, `PROJECT`, `CONFIG_RULE_NAME`, and either `ALLOWED_SECURITY_GROUP_IDS` (comma separated) or `DEMO_SECURITY_GROUP_ID`. `DRY_RUN` defaults to `true`; only the literal `false` enables revocation. Optional `EVIDENCE_BUCKET` receives sanitized JSON under `sg-healing/`.

The handler accepts the specified Config rule's NON_COMPLIANT events, checks the caller account, exact SG allowlist, SG owner, `Project` and `DemoOnly=true` tags, and absence of attached network interfaces. It checks the tags and attachments again immediately before each write. It revokes exact ingress TCP port 22 rules for `0.0.0.0/0` and `::/0`, using rule IDs, then rereads rules up to three times. Private CIDRs, egress and other ports remain untouched. Rules allowing all protocols or a wider port range containing SSH are refused for manual review; the handler will not remove unrelated services implicitly.

Duplicate events re-read current state; an already removed rule is harmless only after verification. API and verification failures raise sanitized exceptions for retry/failure routing. The before/after evidence contains rule IDs, protocols, ports and CIDRs, never rule descriptions or the raw event. `handler_duration_ms` measures handler execution only, **not** Config detection latency or total recovery time. Record the actual injection, Config notification and verified removal timestamps separately during an approved cloud experiment. EC2 has no atomic check-and-revoke transaction with ENI attachment; restrict attachment/tag mutation permissions on the dedicated test SG throughout the experiment.

Terraform's empty ingress configuration is the desired baseline. The temporary test rule is introduced only during an approved isolated experiment, never declared as a persistent Terraform resource. Do not run an infrastructure apply concurrently with that experiment.

`scripts/13-sg-healing-demo.py` implements that real-cloud experiment. Without `--approved-demo`, it runs read-only preflight. Supply `--account`, `--security-group-id`, `--function-name` and `--config-rule` from the approved Terraform environment. Only after explicit approval, add `--approved-demo`; it requires a COMPLIANT Config baseline and the matching Lambda already configured with `DRY_RUN=false`. The caller needs STS identity, EC2 group/rule/ENI reads, Config rule/evaluation reads, Lambda configuration reads, CloudWatch `FilterLogEvents`, and (for the approved run) authorize/revoke ingress on that exact test SG.

The script adds one world TCP22 rule with a unique marker, then polls for actual Config evaluation timestamps, exact-rule Lambda remediation logs, removal of the rule and a subsequent Config COMPLIANT evaluation. It never invokes Lambda or sends a fabricated event. Default timeout is 15 minutes; observed timing is limited by the 10 second polling interval. It writes `evidence/aws/sg-healing-demo.json`. Timeout/API failure triggers cleanup of its own rule and is still reported as failure, never as automatic remediation. A `MANUAL_REVIEW_REQUIRED` cleanup outcome means the operator must inspect the unique rule marker before leaving the test environment.

## Inspector response and worker

Lambda handler: `inspector_response.lambda_handler`. Required environment:

| Name | Purpose |
| --- | --- |
| `EXPECTED_ACCOUNT_ID`, `EXPECTED_REGION`, `PROJECT` | Explicit account/project boundary |
| `ECR_REPOSITORY` | Exact repository name, normally `team4-test` |
| `APPROVED_IMAGE_PARAMETER` | Protected SSM String parameter containing the approval JSON below |
| `IDEMPOTENCY_TABLE` | DynamoDB table with string partition key `id`; rows have no TTL |
| `CODEBUILD_PROJECT` | Externally prepared, trusted project name |
| `CODEBUILD_SERVICE_ROLE_ARN` | Exact expected project service role |
| `REMEDIATION_SOURCE_URL` | Exact GitHub source URL configured on the project |
| `REMEDIATION_SOURCE_REVISION` | Reviewed 40 character commit SHA containing this implementation |
| `CLUSTER_NAME` | Target EKS cluster |
| `DEPLOY_NAMESPACE`, `DEPLOYMENT`, `DEPLOY_CONTAINER` | Normally `demo`, `server`, `test` |
| `SIGNING_IDENTITY`, `SIGNING_ISSUER` | Exact trusted cosign workflow identity and OIDC issuer |
| `DRY_RUN` | Defaults `true`; external CodeBuild project must have the same setting |
| `EVIDENCE_BUCKET` | Optional sanitized Lambda evidence under `inspector/` |

The protected SSM approval contains no secrets. An authorized operator supplies a real, scanned, signed, single-platform image digest and an expiry no more than 24 hours away. Both Lambda and worker can read this parameter; neither may approve or change it. Example shape (the placeholders below intentionally cannot authorize an image):

```json
{
  "approved": false,
  "repository": "team4-test",
  "digest": "REPLACE_WITH_VERIFIED_SHA256_DIGEST",
  "expires_at": "REPLACE_WITH_UTC_EXPIRY"
}
```

Lambda requires an ACTIVE HIGH/CRITICAL package finding for the exact account, region, repository and digest. It rejects events older than 24 hours and confirms the finding with `inspector2:ListFindings`; a synthetic event alone cannot authorize deployment. It checks that the approved replacement exists, is a single-platform manifest, has a completed/active ECR scan and has zero HIGH/CRITICAL findings. A missing or unsafe replacement stops the flow. Approval is a point-in-time decision; the worker performs a fresh scan as well.

Before starting a build, Lambda reads the external project configuration and verifies its source URL, reviewed revision, buildspec, role, nonprivileged environment and fixed deployment/signature variables. The build receives only three event-derived overrides: `BAD_DIGEST`, `SAFE_DIGEST` and `REMEDIATION_ID`; source revision is also pinned explicitly. Build time is bounded to 15 minutes, queue time to 5 minutes.

The external project must use `automation/buildspec-remediate.yml`, the Terraform-exported environment contract and role, and a Linux x86_64 image supporting Python 3, AWS CLI v2, curl, Bash and package installation. `scripts/install-security-tools.sh` installs pinned scanners/signing tools; `automation/install-kubectl.sh` obtains the pinned kubectl and checks its published checksum. Pin and review the build image separately. This project needs network access to the EKS API, ECR, SSM, DynamoDB, log/artifact endpoints, the vulnerability database and tool release hosts. **The baseline public-subnet EKS deployment without NAT does not supply this CodeBuild network path.** Do not widen EKS access to the world to accommodate hosted builds. Prepare a reachable, trusted project explicitly and review any additional network costs.

For a VPC-connected external project, its network administrator must also attach a separately reviewed ENI policy limited to the approved build subnets to the exported service role. Terraform intentionally has no guessed external-network permissions. Apply the exported `encryption_key` and artifact settings as well. These are setup prerequisites; the exported contract alone does not establish working connectivity. See [infrastructure deployment notes](../docs/infra-notes.md).

The worker validates the durable reservation against its exact `CODEBUILD_BUILD_ID`, rechecks account, approval and ECR scan, then queries the Deployment and its owned ReplicaSets/Pods to establish that the vulnerable digest is actually running. It verifies the replacement's cosign identity and runs Trivy without ignoring unfixed HIGH/CRITICAL vulnerabilities. It rechecks approval before mutation, verifies the Deployment identity/generation has not changed, and issues an atomic JSON patch with resource-version, container-name and current-image tests. It waits up to 180 seconds for rollout, checks the observed generation, replica counts and ready Pods' runtime digests, and refuses success while old terminating Pods remain. A rollout failure stops, records failure and leaves the resource for review; it never runs `rollout undo` or selects an arbitrary older tag.

The worker can patch only the configured Deployment under the `team4:image-remediator` RBAC group. Argo CD/Flux-managed workloads are refused: update their reviewed Git source instead. The NetworkPolicy GitOps example can run alongside this worker because it manages policies, not this Deployment's image.

DynamoDB reserves a target/vulnerable-digest pair before starting a build. Changing EventBridge event IDs or CVE IDs does not bypass deduplication. Reservations have **no automatic expiry or deletion**. If StartBuild or recording its result has an uncertain outcome, retries require manual review rather than risking a second deployment. Inspect DynamoDB, CodeBuild, EKS state and failure-queue/CloudWatch events before deliberately resetting a reservation. Lambda reports `BUILD_STARTED`, never deployment success; only the worker's `VERIFIED` result establishes its listed runtime checks. CodeBuild failure events must be routed to the configured failure queue/notification channel.

ECR authentication is held in a temporary Docker config readable only by the worker. Raw commands' outputs, credential values, SSM values and exception bodies are not printed. The temporary config/kubeconfig is removed after execution. Worker evidence is `evidence/inspector-remediation.json`, collected by the CodeBuild artifact configuration; configure its S3 path under `inspector/`.

## Local verification

Run from the repository root. These commands do not connect to AWS or mutate Kubernetes:

```bash
python -m unittest discover -s tests -p 'test_healing*.py' -v
python -m unittest discover -s tests -p 'test_inspector*.py' -v
```

Coverage includes exact SG scope, tags, attached ENIs and attachment races, IPv4/IPv6 and broader-rule refusal, duplicate events, pagination, permission failures, failed verification, authoritative Inspector checks, approval expiry, unsafe/missing/multi-platform replacements, durable deduplication and uncertain starts, external-project configuration, actual workload ownership/digest checks, signature/scan failure, concurrent Deployment edits, rollout failure without rollback, and post-rollout runtime digest checks.

AWS service schemas consulted: [Config compliance notifications](https://docs.aws.amazon.com/config/latest/developerguide/example-config-rule-compliance-notification.html), [Inspector EventBridge finding schema](https://docs.aws.amazon.com/inspector/latest/user/eventbridge-integration.html), [ECR scan results](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_DescribeImageScanFindings.html), and [CodeBuild StartBuild](https://docs.aws.amazon.com/codebuild/latest/APIReference/API_StartBuild.html). CodeBuild's API token alone is short-lived; the durable reservation supplies replay protection.
