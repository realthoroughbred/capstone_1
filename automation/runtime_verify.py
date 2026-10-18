"""Read-only deployment verification, emitting no raw Pod specifications."""

import json
import re
import time
from datetime import datetime, timezone

from .common import digest, require
from .inspector_worker import execute, verify_running_pods


def verify_live_deployments(context, namespace, image, targets, env, run=execute,
                            timeout=60, monotonic=time.monotonic, sleep=time.sleep):
    require(isinstance(image, str) and image.count("@") == 1, "digest_reference_required")
    digest(image.split("@", 1)[1])
    require(bool(targets) and len(targets) == len(set(targets)), "deployment_targets_required")
    require(0 <= timeout <= 300, "invalid_verification_timeout")
    for name in [namespace, *targets]:
        require(re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", name), "invalid_kubernetes_name")
    kube = ["kubectl", "--context", context, "--namespace", namespace, "--request-timeout=30s"]
    def get(resource, name=None):
        args = [*kube, "get", resource]
        if name:
            args.append(name)
        return json.loads(run([*args, "-o", "json"], env=env))
    deadline = monotonic() + timeout
    while True:
        try:
            deployments = [get("deployment", target) for target in targets]
            replicasets, pods = get("replicasets")["items"], get("pods")["items"]
            verified = []
            for target, deployment in zip(targets, deployments):
                metadata = deployment.get("metadata", {})
                require(metadata.get("name") == target and metadata.get("namespace") == namespace,
                        "deployment_target_mismatch")
                count = verify_running_pods(deployment, replicasets, pods, "test", image, after=True)
                verified.append({"deployment": target, "uid": metadata["uid"],
                                 "generation": metadata["generation"], "ready_replicas": count,
                                 "verified_image": image})
            return {"status": "VERIFIED", "verification": "PASS", "evidence_kind": "KUBERNETES_API_OBSERVATION",
                    "context": context, "namespace": namespace, "deployments": verified,
                    "observed_at": datetime.now(timezone.utc).isoformat()}
        except Exception:
            if monotonic() >= deadline:
                return {"status": "FAILED", "verification": "FAIL", "evidence_kind": "KUBERNETES_API_ATTEMPT",
                        "reason": "runtime_digest_readiness_or_snapshot_check_failed",
                        "context": context, "namespace": namespace,
                        "observed_at": datetime.now(timezone.utc).isoformat()}
            sleep(min(5, max(0, deadline - monotonic())))
