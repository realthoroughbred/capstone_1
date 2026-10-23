"""Validate an Inspector finding and enqueue one bounded, approved remediation.

BUILD_STARTED is not deployment success. The CodeBuild worker must independently
check the running workload, approval, scan and signature before replacing it.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

try:
    from .common import Rejected, audit, aws_error_code, digest, dry_run, evidence, identity, require, required, timestamp
except ImportError:
    from common import Rejected, audit, aws_error_code, digest, dry_run, evidence, identity, require, required, timestamp


def finding_image(finding, account, region, repository):
    require(finding.get("awsAccountId") == account, "finding_account_mismatch")
    require(finding.get("status") == "ACTIVE", "finding_not_active")
    require(finding.get("severity") in ("HIGH", "CRITICAL"), "finding_below_threshold")
    require(finding.get("type") == "PACKAGE_VULNERABILITY", "unsupported_finding_type")
    resources = finding.get("resources", [])
    require(len(resources) == 1, "ambiguous_finding_resources")
    resource = resources[0]
    require(resource.get("type") == "AWS_ECR_CONTAINER_IMAGE"
            and resource.get("region") == region
            and resource.get("partition") == "aws", "finding_resource_scope_mismatch")
    image = resource.get("details", {}).get("awsEcrContainerImage", {})
    require(image.get("registry") == account and image.get("repositoryName") == repository,
            "finding_repository_mismatch")
    image_digest = digest(image.get("imageHash"))
    expected_id = f"arn:aws:ecr:{region}:{account}:repository/{repository}/{image_digest}"
    require(resource.get("id") == expected_id, "finding_resource_id_mismatch")
    return image_digest


def approved_image(parameter_value, repository, now):
    try:
        approval = json.loads(parameter_value)
    except (TypeError, ValueError):
        raise Rejected("invalid_image_approval") from None
    require(isinstance(approval, dict), "invalid_image_approval")
    require(approval.get("approved") is True and approval.get("repository") == repository,
            "image_not_approved")
    expiry = timestamp(approval.get("expires_at"))
    require(now < expiry and (expiry - now).total_seconds() <= 86400,
            "image_approval_expired_or_too_long")
    return digest(approval.get("digest"))


def _verify_safe_ecr(ecr, account, repository, safe):
    response = ecr.describe_images(registryId=account, repositoryName=repository,
                                   imageIds=[{"imageDigest": safe}])
    images = response.get("imageDetails", [])
    require(len(images) == 1 and images[0].get("imageDigest") == safe, "approved_image_missing")
    require(images[0].get("imageManifestMediaType") in (
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json"), "multi_arch_image_requires_manual_review")
    scan = ecr.describe_image_scan_findings(registryId=account, repositoryName=repository,
                                           imageId={"imageDigest": safe})
    require(scan.get("registryId") == account and scan.get("repositoryName") == repository
            and scan.get("imageId", {}).get("imageDigest") == safe, "scan_image_mismatch")
    require(scan.get("imageScanStatus", {}).get("status") in ("ACTIVE", "COMPLETE"),
            "approved_image_scan_not_ready")
    findings = scan.get("imageScanFindings", {})
    require("findingSeverityCounts" in findings and bool(findings.get("imageScanCompletedAt")),
            "approved_image_scan_missing")
    counts = findings["findingSeverityCounts"]
    require(isinstance(counts, dict)
            and counts.get("HIGH", 0) == 0 and counts.get("CRITICAL", 0) == 0,
            "approved_image_is_vulnerable")


def verify_build_project(codebuild, env, account, region):
    name = required(env, "CODEBUILD_PROJECT")
    revision = required(env, "REMEDIATION_SOURCE_REVISION")
    require(re.fullmatch(r"[a-f0-9]{40}", revision), "invalid_reviewed_source_revision")
    response = codebuild.batch_get_projects(names=[name])
    projects = response.get("projects", [])
    require(len(projects) == 1 and not response.get("projectsNotFound"), "build_project_missing")
    project = projects[0]
    source = project.get("source", {})
    environment = project.get("environment", {})
    require(project.get("name") == name
            and project.get("arn") == f"arn:aws:codebuild:{region}:{account}:project/{name}",
            "build_project_scope_mismatch")
    require(project.get("serviceRole") == required(env, "CODEBUILD_SERVICE_ROLE_ARN"), "build_role_mismatch")
    require(project.get("sourceVersion") == revision and source.get("type") == "GITHUB"
            and source.get("location") == required(env, "REMEDIATION_SOURCE_URL")
            and source.get("buildspec") == "automation/buildspec-remediate.yml", "build_source_mismatch")
    require(environment.get("privilegedMode") is False, "privileged_build_not_allowed")
    values = {item.get("name"): item for item in environment.get("environmentVariables", [])}
    for key in ("EXPECTED_ACCOUNT_ID", "EXPECTED_REGION", "PROJECT", "ECR_REPOSITORY",
                "APPROVED_IMAGE_PARAMETER", "IDEMPOTENCY_TABLE", "CLUSTER_NAME", "DEPLOY_NAMESPACE",
                "DEPLOYMENT", "DEPLOY_CONTAINER", "SIGNING_IDENTITY", "SIGNING_ISSUER"):
        require(values.get(key, {}).get("value") == required(env, key)
                and values.get(key, {}).get("type") == "PLAINTEXT", "build_environment_mismatch_" + key)
    expected_dry = "true" if dry_run(env) else "false"
    require(values.get("DRY_RUN", {}).get("value") == expected_dry
            and values.get("DRY_RUN", {}).get("type") == "PLAINTEXT", "build_environment_mismatch_DRY_RUN")
    return revision


def respond(event, env, clients, now=None):
    now = now or datetime.now(timezone.utc)
    account, region = identity(env)
    dry = dry_run(env)
    repository = required(env, "ECR_REPOSITORY")
    require(event.get("source") == "aws.inspector2"
            and event.get("detail-type") == "Inspector2 Finding", "unexpected_event_type")
    require(event.get("account") == account and event.get("region") == region, "event_scope_mismatch")
    age = (now - timestamp(event.get("time"))).total_seconds()
    require(-300 <= age <= 86400, "stale_or_future_event")
    detail = event.get("detail", {})
    if detail.get("status") != "ACTIVE" or detail.get("severity") not in ("HIGH", "CRITICAL"):
        return {"status": "IGNORED", "reason": "inactive_or_below_threshold", "dry_run": dry}
    bad = finding_image(detail, account, region, repository)
    finding_arn = detail.get("findingArn", "")
    require(finding_arn.startswith(f"arn:aws:inspector2:{region}:{account}:finding/")
            and len(finding_arn.rsplit("/", 1)[-1]) > 0, "finding_arn_scope_mismatch")
    require(clients["sts"].get_caller_identity().get("Account") == account, "caller_account_mismatch")
    # Event detail is a hint only. Confirm the finding with AWS before any action.
    response = clients["inspector2"].list_findings(filterCriteria={
        "findingArn": [{"comparison": "EQUALS", "value": finding_arn}]}, maxResults=10)
    findings = response.get("findings", [])
    require(len(findings) == 1 and not response.get("nextToken"), "authoritative_finding_missing")
    require(findings[0].get("findingArn") == finding_arn
            and finding_image(findings[0], account, region, repository) == bad,
            "authoritative_finding_mismatch")
    parameter = clients["ssm"].get_parameter(Name=required(env, "APPROVED_IMAGE_PARAMETER"), WithDecryption=False)
    safe = approved_image(parameter.get("Parameter", {}).get("Value"), repository, now)
    require(safe != bad, "replacement_is_vulnerable_digest")
    _verify_safe_ecr(clients["ecr"], account, repository, safe)
    revision = verify_build_project(clients["codebuild"], env, account, region)
    target = [required(env, key) for key in (
        "PROJECT", "CLUSTER_NAME", "DEPLOY_NAMESPACE", "DEPLOYMENT", "DEPLOY_CONTAINER")]
    # Dedup by vulnerable digest AND target, independent of event ID or finding ID.
    # Rows have no TTL: aged/replayed events cannot silently start a second build.
    key = hashlib.sha256(json.dumps([account, region, repository, *target, bad],
                                    separators=(",", ":")).encode()).hexdigest()
    result = {"status": "DRY_RUN", "dry_run": dry, "remediation_id": key,
              "bad_digest": bad, "safe_digest": safe, "repository": repository,
              "verification": "NOT_EXECUTED", "evidence_kind": "AWS_API_CONFIRMED_FINDING"}
    result["event_origin"] = ("SIMULATED_EVENT" if event.get("_evidence_kind") == "SIMULATED_FIXTURE"
                              else "INSPECTOR_EVENT")
    if dry:
        return result
    table = required(env, "IDEMPOTENCY_TABLE")
    project_name = required(env, "CODEBUILD_PROJECT")
    db = clients["dynamodb"]
    try:
        db.put_item(TableName=table, Item={
            "id": {"S": key}, "status": {"S": "RESERVED"},
            "bad_digest": {"S": bad}, "safe_digest": {"S": safe},
            "event_origin": {"S": result["event_origin"]},
            "created_at": {"S": now.isoformat()}}, ConditionExpression="attribute_not_exists(id)")
    except Exception as exc:
        if aws_error_code(exc) != "ConditionalCheckFailedException":
            raise RuntimeError("deduplication_unavailable") from None
        existing = db.get_item(TableName=table, Key={"id": {"S": key}}, ConsistentRead=True).get("Item", {})
        state = existing.get("status", {}).get("S")
        if state not in ("BUILD_STARTED", "VERIFIED", "NOT_DEPLOYED", "DRY_RUN"):
            raise RuntimeError("previous_attempt_requires_manual_review")
        return dict(result, status="DUPLICATE", previous_status=state)
    try:
        build = clients["codebuild"].start_build(
            projectName=project_name, idempotencyToken=key,
            sourceVersion=revision,
            timeoutInMinutesOverride=15, queuedTimeoutInMinutesOverride=5,
            environmentVariablesOverride=[
                {"name": "BAD_DIGEST", "value": bad, "type": "PLAINTEXT"},
                {"name": "SAFE_DIGEST", "value": safe, "type": "PLAINTEXT"},
                {"name": "REMEDIATION_ID", "value": key, "type": "PLAINTEXT"}])
        build_id = build.get("build", {}).get("id")
        require(isinstance(build_id, str) and build_id.startswith(project_name + ":"), "invalid_build_response")
        db.update_item(TableName=table, Key={"id": {"S": key}},
                       UpdateExpression="SET #s = :state, build_id = :build",
                       ConditionExpression="#s = :reserved",
                       ExpressionAttributeNames={"#s": "status"},
                       ExpressionAttributeValues={":state": {"S": "BUILD_STARTED"},
                                                  ":build": {"S": build_id},
                                                  ":reserved": {"S": "RESERVED"}})
    except Exception:
        # Never delete the reservation after an uncertain API outcome. A build
        # might have started. Operators inspect this row/build before any retry.
        raise RuntimeError("build_start_outcome_requires_manual_review") from None
    return dict(result, status="BUILD_STARTED", build_id=build_id)


def lambda_handler(event, context):
    import boto3
    from botocore.config import Config
    config = Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2, "mode": "standard"})
    try:
        clients = {service: boto3.client(service, region_name=os.environ.get("EXPECTED_REGION"), config=config)
                   for service in ("sts", "inspector2", "ssm", "ecr", "dynamodb", "codebuild")}
        result = respond(event, os.environ, clients)
        return evidence(result, os.environ,
                        boto3.client("s3", region_name=os.environ.get("EXPECTED_REGION"), config=config), "inspector")
    except Rejected as exc:
        return audit({"status": "REJECTED", "reason": str(exc)})
    except Exception:
        audit({"status": "FAILED", "reason": "inspector_response_requires_review"})
        raise RuntimeError("inspector_response_requires_review") from None
