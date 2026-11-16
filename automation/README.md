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

### Slack report (optional)

`sg_healing.handle` reports each result to a Slack Incoming Webhook after the revoke and the S3 evidence write. It reports `REMEDIATED`, `DRY_RUN`, `REJECTED` and `FAILED`; `IGNORED` and `ALREADY_COMPLIANT` (duplicate events) send nothing. The Block Kit message (`common.slack_message`, colour bar per status) shows project, status, target SG ID, action, time, run time and, for `REJECTED`/`FAILED`, the reason code. The run time is `handler_duration_ms` when present, otherwise the time since the handler started.

- **Slack never changes the outcome.** `common.notify_slack` and the handler's `report` catch everything, so a Slack, network or Secrets Manager problem can neither replace a result or exception nor delay the revoke (the report runs last). A retried failure reports once per attempt.
- **`REMEDIATED` stays `REMEDIATED` when the evidence write fails.** The revoke is already final, so the report carries the real status plus a notice that the S3 evidence was not saved. The invocation still fails with `remediation_or_verification_failed` so Lambda retries and routes to the failure queue, and the log gets the real result (`evidence_saved: false`) and `{"status":"FAILED","reason":"evidence_write_failed"}`. The retry sees `ALREADY_COMPLIANT`, which is silent.
- **`REJECTED` does not claim the group is unchanged.** Tags, attachments and ownership are rechecked before every revoke and once after the last one, so a refusal can follow earlier revokes (for example the IPv4 rule removed, then an ENI attached before the IPv6 rule). The message says rules may already be gone and asks for a check of the current rules.
- **Limits.** The secret client makes one attempt (`total_max_attempts=1`, 2 s connect, 3 s read; `max_attempts` would count retries after the first request). The POST has a 3 s per-operation timeout and refuses redirects. DNS lookups are not covered by either timeout. `urllib.request` is imported only when a message is posted, so cold starts without Slack do not load it.
- **Secret handling.** The environment holds only the secret's ARN. The URL must start with `https://hooks.slack.com/services/`, is read per notification, and is never logged, returned or stored. Only constant codes are logged: `slack_notification: SENT|FAILED` with `slack_secret_unavailable`, `slack_webhook_missing`, `slack_webhook_invalid`, `slack_post_failed` or `slack_notification_error`. A failed report is visible only in the log; there is no alarm on it.

Without `SLACK_WEBHOOK_SECRET_ARN` the feature is off. Nothing in the repository's tests contacts Slack, and the payload has not been posted to a real webhook. Send one test message to a throwaway channel before relying on it.

**Setup.** Nothing below runs automatically, and this repository's tests never run `terraform apply`.

1. In Slack, create an Incoming Webhook for the target channel and keep the URL private.
2. An IAM administrator publishes the updated `iam/team4-runtime-boundary.json` (statement `SlackWebhookSecretReader`: `secretsmanager:GetSecretValue` on `team4/notifications/slack-webhook-*`) as a new version of the admin-managed `team4-runtime-boundary` policy, and updates `iam/team4-operator-provisioning.json` (the same secret name added to the `Services` resources). `docs/admin-bootstrap/render.py` renders the boundary; it must stay within 6144 characters and is at about 5.9 k with this statement. Without the boundary update the Lambda is denied at run time and logs `slack_secret_unavailable`; without the provisioning update `CreateSecret` is denied at apply.
3. In the untracked `infra/terraform.tfvars` set both flags, then review a fresh plan and apply it only under the project's cost and permission approval:

   ```hcl
   enable_self_healing       = true
   enable_slack_notification = true
   ```

   The plan should add `aws_secretsmanager_secret.slack_webhook` (`<project>/notifications/slack-webhook`, project KMS key, 7-day recovery window, **no secret value**), set `SLACK_WEBHOOK_SECRET_ARN` on the Lambda and add one IAM statement allowing `secretsmanager:GetSecretValue` on that secret only. `enable_slack_notification` without `enable_self_healing` fails validation. `healing_dry_run` keeps its default, so the first messages are `DRY_RUN`.
4. Store the URL. The operator policies allow `UpdateSecret` on this secret (with KMS use on project-tagged keys) but not `PutSecretValue` or `GetSecretValue`, so use `update-secret`:

   ```bash
   export AWS_PROFILE=team4 AWS_REGION=ap-northeast-2 AWS_PAGER=""
   umask 077
   webhook_file="$(mktemp)"
   read -rsp 'Slack Incoming Webhook URL: ' webhook_url; echo
   printf '%s' "$webhook_url" > "$webhook_file"; unset webhook_url
   aws secretsmanager update-secret --secret-id team4/notifications/slack-webhook \
     --secret-string "file://$webhook_file"
   shred -u "$webhook_file" 2>/dev/null || rm -f "$webhook_file"
   ```

   The value may be the plain URL or JSON `{"webhook_url": "https://hooks.slack.com/services/..."}`. Until a value exists the Lambda logs `slack_secret_unavailable`.
5. Check without reading the value: `aws secretsmanager describe-secret --secret-id team4/notifications/slack-webhook --query VersionIdsToStages` must list a version with `AWSCURRENT`. After an event, `/aws/lambda/team4-sg-healing` contains `"slack_notification":"SENT"`.

To rotate, create a new webhook in Slack, repeat step 4 and revoke the old one; nothing is cached. On destroy the secret enters its 7-day recovery window, and the same name cannot be created again until it is restored (`aws secretsmanager restore-secret`) or the window ends.

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

`tests/test_healing_slack.py` covers the Slack report with fake clients and a throwaway `127.0.0.1` HTTP server: each status message, send/secret/URL failures, the evidence-failure and partial-rejection cases, the Lambda entry point with stubbed boto3 (secret client retry settings), lazy import of `urllib.request`, and isolation of the handler's result and exceptions from Slack failures.

AWS service schemas consulted: [Config compliance notifications](https://docs.aws.amazon.com/config/latest/developerguide/example-config-rule-compliance-notification.html), [Inspector EventBridge finding schema](https://docs.aws.amazon.com/inspector/latest/user/eventbridge-integration.html), [ECR scan results](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_DescribeImageScanFindings.html), and [CodeBuild StartBuild](https://docs.aws.amazon.com/codebuild/latest/APIReference/API_StartBuild.html). CodeBuild's API token alone is short-lived; the durable reservation supplies replay protection.
