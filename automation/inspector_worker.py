"""Bounded CodeBuild worker. Never selects an arbitrary previous image or rolls back.

Runs only in a configured CodeBuild project with access to the target EKS API.
Commands use argument arrays and captured output; tokens and raw errors are not logged.
"""

import base64
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from .common import audit, digest, dry_run, identity, require, required
    from .inspector_response import approved_image, _verify_safe_ecr
except ImportError:
    from common import audit, digest, dry_run, identity, require, required
    from inspector_response import approved_image, _verify_safe_ecr


def execute(args, *, env, timeout=60):
    try:
        response = subprocess.run(args, capture_output=True, text=True, check=False,
                                  env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("command_unavailable_or_timed_out") from None
    if response.returncode:
        raise RuntimeError("command_failed")
    return response.stdout


class AwsService:
    def __init__(self, service, env, run):
        self.service, self.env, self.run = service, env, run

    def __getattr__(self, operation):
        def call(**kwargs):
            args = ["aws", self.service, operation.replace("_", "-"), "--region",
                    self.env["EXPECTED_REGION"], "--no-cli-pager", "--output", "json"]
            if kwargs:
                args.extend(["--cli-input-json", json.dumps(kwargs, separators=(",", ":"))])
            result = self.run(args, env=self.env)
            return json.loads(result) if result.strip() else {}
        return call


def deployment_patch(deployment, container, bad_image, safe_image):
    require(not deployment.get("metadata", {}).get("deletionTimestamp"), "deployment_is_terminating")
    metadata = deployment.get("metadata", {})
    labels = metadata.get("labels", {})
    annotations = metadata.get("annotations", {})
    require(not labels.get("argocd.argoproj.io/instance")
            and not annotations.get("argocd.argoproj.io/tracking-id")
            and not labels.get("kustomize.toolkit.fluxcd.io/name"), "gitops_workload_requires_git_change")
    containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    matches = [(index, item) for index, item in enumerate(containers) if item.get("name") == container]
    require(len(matches) == 1, "deployment_container_mismatch")
    index, current = matches[0]
    if current.get("image") != bad_image:
        return None
    require(deployment.get("spec", {}).get("replicas", 1) > 0, "deployment_scaled_to_zero")
    require(isinstance(metadata.get("resourceVersion"), str) and bool(metadata.get("uid")),
            "deployment_identity_missing")
    return [
        {"op": "test", "path": "/metadata/resourceVersion", "value": metadata["resourceVersion"]},
        {"op": "test", "path": f"/spec/template/spec/containers/{index}/name", "value": container},
        {"op": "test", "path": f"/spec/template/spec/containers/{index}/image", "value": bad_image},
        {"op": "replace", "path": f"/spec/template/spec/containers/{index}/image", "value": safe_image},
    ]


def owned_pods(deployment, replicasets, pods):
    uid = deployment.get("metadata", {}).get("uid")
    require(bool(uid), "deployment_identity_missing")
    owned_rs = {rs.get("metadata", {}).get("uid") for rs in replicasets if any(
        ref.get("uid") == uid and ref.get("kind") == "Deployment" and ref.get("controller") is True
        for ref in rs.get("metadata", {}).get("ownerReferences", []))}
    return [pod for pod in pods if any(
        ref.get("uid") in owned_rs and ref.get("kind") == "ReplicaSet" and ref.get("controller") is True
        for ref in pod.get("metadata", {}).get("ownerReferences", []))]


def verify_running_pods(deployment, replicasets, pods, container, image, *, after=False):
    selected = owned_pods(deployment, replicasets, pods)
    image_digest = image.rsplit("@", 1)[-1]
    active = [pod for pod in selected if not pod.get("metadata", {}).get("deletionTimestamp")]
    require(bool(active), "no_owned_running_pods")
    matched = []
    for pod in active:
        statuses = [item for item in pod.get("status", {}).get("containerStatuses", [])
                    if item.get("name") == container]
        specs = [item for item in pod.get("spec", {}).get("containers", []) if item.get("name") == container]
        good = (len(statuses) == 1 and len(specs) == 1 and specs[0].get("image") == image
                and statuses[0].get("ready") is True
                and statuses[0].get("imageID", "").split("://", 1)[-1].rsplit("@", 1)[-1] == image_digest)
        if good:
            matched.append(pod)
        elif after:
            raise RuntimeError("post_rollout_pod_image_or_readiness_mismatch")
    require(bool(matched), "vulnerable_digest_not_running" if not after else "replacement_not_running")
    if after:
        templates = [item for item in deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
                     if item.get("name") == container]
        require(len(templates) == 1 and templates[0].get("image") == image, "replacement_template_changed")
        desired = deployment.get("spec", {}).get("replicas", 1)
        status = deployment.get("status", {})
        require(status.get("observedGeneration", 0) >= deployment.get("metadata", {}).get("generation", 1),
                "deployment_generation_not_observed")
        require(len(matched) == desired and status.get("updatedReplicas", 0) == desired
                and status.get("availableReplicas", 0) == desired, "replacement_replicas_not_available")
        # Terminating old Pods can still carry the vulnerable digest. Do not
        # claim successful remediation until they have disappeared as well.
        require(all(pod in active for pod in selected), "old_pods_still_terminating")
    return len(matched)


def work(env, run=execute, now=None):
    env = dict(env)
    fixed_now = now
    now = now or datetime.now(timezone.utc)
    account, region = identity(env)
    dry = dry_run(env)
    bad, safe = digest(required(env, "BAD_DIGEST")), digest(required(env, "SAFE_DIGEST"))
    require(bad != safe, "replacement_is_vulnerable_digest")
    key = required(env, "REMEDIATION_ID")
    require(re.fullmatch(r"[a-f0-9]{64}", key), "invalid_remediation_id")
    build_id = required(env, "CODEBUILD_BUILD_ID")
    table = required(env, "IDEMPOTENCY_TABLE")
    repository = required(env, "ECR_REPOSITORY")
    cluster = required(env, "CLUSTER_NAME")
    namespace = required(env, "DEPLOY_NAMESPACE")
    target = required(env, "DEPLOYMENT")
    container = required(env, "DEPLOY_CONTAINER")
    signing_identity = required(env, "SIGNING_IDENTITY")
    signing_issuer = required(env, "SIGNING_ISSUER")
    env.update(AWS_REGION=region, AWS_DEFAULT_REGION=region, AWS_PAGER="")
    db = AwsService("dynamodb", env, run)
    row = db.get_item(TableName=table, Key={"id": {"S": key}}, ConsistentRead=True).get("Item", {})
    require(row.get("status", {}).get("S") == "BUILD_STARTED"
            and row.get("build_id", {}).get("S") == build_id
            and row.get("bad_digest", {}).get("S") == bad
            and row.get("safe_digest", {}).get("S") == safe, "build_reservation_mismatch")
    result = {"status": "FAILED", "remediation_id": key, "build_id": build_id,
              "dry_run": dry, "bad_digest": bad, "safe_digest": safe,
              "verification": "NOT_EXECUTED", "evidence_kind": "AWS_CODEBUILD_EXECUTION"}
    origin = row.get("event_origin", {}).get("S")
    result["event_origin"] = origin if origin in ("SIMULATED_EVENT", "INSPECTOR_EVENT") else "UNSPECIFIED"
    stage = "identity"
    try:
        require(AwsService("sts", env, run).get_caller_identity().get("Account") == account,
                "caller_account_mismatch")
        stage = "approval_and_ecr_scan"
        approval = AwsService("ssm", env, run).get_parameter(
            Name=required(env, "APPROVED_IMAGE_PARAMETER"), WithDecryption=False)
        require(approved_image(approval.get("Parameter", {}).get("Value"), repository, now) == safe,
                "approval_changed")
        _verify_safe_ecr(AwsService("ecr", env, run), account, repository, safe)
        registry = f"{account}.dkr.ecr.{region}.amazonaws.com"
        bad_image, safe_image = f"{registry}/{repository}@{bad}", f"{registry}/{repository}@{safe}"
        with tempfile.TemporaryDirectory(prefix="remediation-") as temp:
            env["KUBECONFIG"] = str(Path(temp) / "kubeconfig")
            env["DOCKER_CONFIG"] = str(Path(temp) / "docker")
            Path(env["DOCKER_CONFIG"]).mkdir(mode=0o700)
            stage = "cluster_connection"
            run(["aws", "eks", "update-kubeconfig", "--name", cluster, "--region", region,
                 "--kubeconfig", env["KUBECONFIG"], "--alias", cluster], env=env)
            kube = ["kubectl", "--context", cluster, "--namespace", namespace, "--request-timeout=30s"]
            def get(resource, name=None):
                args = [*kube, "get", resource]
                if name:
                    args.append(name)
                return json.loads(run([*args, "-o", "json"], env=env))
            stage = "current_workload"
            deployment = get("deployment", target)
            patch = deployment_patch(deployment, container, bad_image, safe_image)
            if patch is None:
                result.update(status="NOT_DEPLOYED", verification="NO_CHANGE_NEEDED")
            else:
                verify_running_pods(deployment, get("replicasets")["items"], get("pods")["items"],
                                    container, bad_image)
                stage = "signature_and_fresh_scan"
                password = run(["aws", "ecr", "get-login-password", "--region", region], env=env).strip()
                require(bool(password), "registry_authentication_missing")
                auth_file = Path(env["DOCKER_CONFIG"]) / "config.json"
                auth_file.write_text(json.dumps({"auths": {registry: {
                    "auth": base64.b64encode(("AWS:" + password).encode()).decode()}}}), encoding="utf-8")
                auth_file.chmod(0o600)
                run(["cosign", "verify", "--certificate-identity", signing_identity,
                     "--certificate-oidc-issuer", signing_issuer, safe_image], env=env, timeout=120)
                scan_path = str(Path(temp) / "trivy.json")
                run(["trivy", "image", "--quiet", "--scanners", "vuln", "--severity", "HIGH,CRITICAL",
                     "--exit-code", "1", "--format", "json", "--output", scan_path,
                     safe_image], env=env, timeout=300)
                # Approval can expire while downloading the vulnerability DB.
                approval = AwsService("ssm", env, run).get_parameter(
                    Name=env["APPROVED_IMAGE_PARAMETER"], WithDecryption=False)
                require(approved_image(approval.get("Parameter", {}).get("Value"), repository,
                                       fixed_now or datetime.now(timezone.utc)) == safe,
                        "approval_changed")
                if dry:
                    result.update(status="DRY_RUN", verification="NOT_EXECUTED")
                else:
                    stage = "atomic_image_replace"
                    latest = get("deployment", target)
                    require(latest["metadata"].get("uid") == deployment["metadata"].get("uid")
                            and latest["metadata"].get("generation") == deployment["metadata"].get("generation"),
                            "deployment_changed_during_scan")
                    patch = deployment_patch(latest, container, bad_image, safe_image)
                    require(patch is not None, "deployment_image_changed_during_scan")
                    # The JSON test operations reject concurrent edits. Do not
                    # re-read and overwrite another deployment decision.
                    run([*kube, "patch", "deployment", target, "--type=json", "-p",
                         json.dumps(patch, separators=(",", ":"))], env=env)
                    stage = "rollout_verification"
                    run([*kube, "rollout", "status", f"deployment/{target}", "--timeout=180s"],
                        env=env, timeout=210)
                    updated = get("deployment", target)
                    require(updated["metadata"]["uid"] == deployment["metadata"]["uid"], "deployment_recreated")
                    verify_running_pods(updated, get("replicasets")["items"], get("pods")["items"],
                                        container, safe_image, after=True)
                    result.update(status="VERIFIED", verification="PASS")
    except Exception:
        # A rollout failure stops here. There is no rollback to an unverified image.
        result.update(status="FAILED", failed_stage=stage, verification="FAIL")
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    Path("evidence").mkdir(exist_ok=True)
    Path("evidence/inspector-remediation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    audit(result)
    db.update_item(TableName=table, Key={"id": {"S": key}},
                   UpdateExpression="SET #s = :state, finished_at = :finished",
                   ConditionExpression="build_id = :build AND #s = :started",
                   ExpressionAttributeNames={"#s": "status"},
                   ExpressionAttributeValues={":state": {"S": result["status"]},
                                              ":finished": {"S": result["finished_at"]},
                                              ":build": {"S": build_id},
                                              ":started": {"S": "BUILD_STARTED"}})
    return result


if __name__ == "__main__":
    try:
        outcome = work(os.environ)
        raise SystemExit(1 if outcome["status"] == "FAILED" else 0)
    except Exception:
        audit({"status": "FAILED", "reason": "worker_precondition_or_evidence_failure"})
        raise SystemExit(1) from None
