"""Simulated complete worker flow, including rollout and atomic change guards."""

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from automation.common import Rejected
from automation.inspector_worker import deployment_patch, verify_running_pods, work
from automation.runtime_verify import verify_live_deployments


ACCOUNT = "123456789012"
BAD, SAFE = "sha256:" + "a" * 64, "sha256:" + "b" * 64
REPO = ACCOUNT + ".dkr.ecr.ap-northeast-2.amazonaws.com/team4-test"
NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)
ENV = {"EXPECTED_ACCOUNT_ID": ACCOUNT, "EXPECTED_REGION": "ap-northeast-2", "PROJECT": "team4",
       "ECR_REPOSITORY": "team4-test", "CLUSTER_NAME": "team4-eks", "DEPLOY_NAMESPACE": "demo",
       "DEPLOYMENT": "server", "DEPLOY_CONTAINER": "test", "APPROVED_IMAGE_PARAMETER": "/team4/approved-image",
       "IDEMPOTENCY_TABLE": "team4-remediation", "REMEDIATION_ID": "c" * 64,
       "BAD_DIGEST": BAD, "SAFE_DIGEST": SAFE, "CODEBUILD_BUILD_ID": "team4-remediate:example-build",
       "SIGNING_IDENTITY": "https://github.com/realthoroughbred/capstone_1/.github/workflows/deploy.yml@refs/heads/main",
       "SIGNING_ISSUER": "https://token.actions.githubusercontent.com"}


def deployment(image=REPO + "@" + BAD):
    return {"metadata": {"name": "server", "uid": "deployment-uid", "resourceVersion": "1", "generation": 1},
            "spec": {"replicas": 1, "template": {"spec": {"containers": [{"name": "test", "image": image}]}}},
            "status": {"observedGeneration": 1, "updatedReplicas": 1, "availableReplicas": 1}}


def pod(image=REPO + "@" + BAD):
    return {"metadata": {"name": "server-pod", "uid": "pod-uid", "ownerReferences": [
        {"uid": "rs-uid", "kind": "ReplicaSet", "controller": True}]},
        "spec": {"containers": [{"name": "test", "image": image}]},
        "status": {"containerStatuses": [{"name": "test", "ready": True, "imageID": "containerd://" + image}]}}


RS = [{"metadata": {"uid": "rs-uid", "ownerReferences": [
    {"uid": "deployment-uid", "kind": "Deployment", "controller": True}]}}]


class Runner:
    def __init__(self):
        self.calls = []
        self.changed = False
        self.fail_command = None
        self.approval_digest = SAFE
        self.initial_image = REPO + "@" + BAD
        self.bad_owner = False
        self.race = False
        self.deployment_gets = 0
        self.verification_bad_digest = False

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if self.fail_command and self.fail_command in args:
            raise RuntimeError("simulated failure with SECRET_NEVER_LOG")
        if args[0] == "aws":
            service, command = args[1:3]
            if (service, command) == ("dynamodb", "get-item"):
                return json.dumps({"Item": {name: {"S": value} for name, value in {
                    "status": "BUILD_STARTED", "build_id": ENV["CODEBUILD_BUILD_ID"],
                    "bad_digest": BAD, "safe_digest": SAFE}.items()}})
            if (service, command) == ("sts", "get-caller-identity"):
                return json.dumps({"Account": ACCOUNT})
            if (service, command) == ("ssm", "get-parameter"):
                return json.dumps({"Parameter": {"Value": json.dumps({"approved": True,
                    "repository": "team4-test", "digest": self.approval_digest,
                    "expires_at": "2026-10-18T01:00:00Z"})}})
            if (service, command) == ("ecr", "describe-images"):
                return json.dumps({"imageDetails": [{"imageDigest": SAFE,
                    "imageManifestMediaType": "application/vnd.oci.image.manifest.v1+json"}]})
            if (service, command) == ("ecr", "describe-image-scan-findings"):
                return json.dumps({"registryId": ACCOUNT, "repositoryName": "team4-test",
                    "imageId": {"imageDigest": SAFE}, "imageScanStatus": {"status": "ACTIVE"},
                    "imageScanFindings": {"imageScanCompletedAt": NOW.isoformat(), "findingSeverityCounts": {}}})
            if (service, command) == ("ecr", "get-login-password"):
                return "SECRET_NEVER_LOG"
            return "{}"
        if args[0] == "kubectl":
            if "patch" in args:
                self.changed = True
                return "{}"
            if "rollout" in args:
                return "deployment successfully rolled out"
            resource = args[args.index("get") + 1]
            current = REPO + "@" + SAFE if self.changed else self.initial_image
            if resource == "deployment":
                self.deployment_gets += 1
                item = deployment(current)
                if self.race and self.deployment_gets > 1:
                    item["metadata"]["generation"] = 2
                return json.dumps(item)
            if resource == "replicasets":
                return json.dumps({"items": [] if self.bad_owner else RS})
            if resource == "pods":
                if self.changed and self.verification_bad_digest:
                    current = REPO + "@" + BAD
                return json.dumps({"items": [pod(current)]})
        if args[0] == "trivy":
            Path(args[args.index("--output") + 1]).write_text('{"Results": []}')
        return "{}"


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.runner = Runner()
        self.env = dict(ENV)
        self.temp = tempfile.TemporaryDirectory()
        self.previous_cwd = os.getcwd()
        os.chdir(self.temp.name)
        self.output = io.StringIO()

    def tearDown(self):
        os.chdir(self.previous_cwd)
        self.temp.cleanup()

    def run_worker(self):
        with redirect_stdout(self.output):
            return work(self.env, self.runner, NOW)

    def mutations(self):
        return [args for args in self.runner.calls if args[0] == "kubectl" and "patch" in args]

    def test_default_dry_run_has_no_kubernetes_mutation(self):
        result = self.run_worker()
        self.assertEqual("DRY_RUN", result["status"])
        self.assertEqual([], self.mutations())
        self.assertIn("cosign", [args[0] for args in self.runner.calls])
        self.assertIn("trivy", [args[0] for args in self.runner.calls])

    def test_approved_replacement_is_atomic_and_verified(self):
        self.env["DRY_RUN"] = "false"
        self.assertEqual("VERIFIED", self.run_worker()["status"])
        self.assertEqual(1, len(self.mutations()))
        command = self.mutations()[0]
        operations = json.loads(command[command.index("-p") + 1])
        self.assertEqual(["test", "test", "test", "replace"], [op["op"] for op in operations])
        evidence = json.loads(Path("evidence/inspector-remediation.json").read_text())
        self.assertEqual("PASS", evidence["verification"])
        self.assertNotIn("SECRET_NEVER_LOG", self.output.getvalue())
        self.assertNotIn("SECRET_NEVER_LOG", json.dumps(evidence))

    def test_stale_finding_does_not_replace_other_image(self):
        self.runner.initial_image = REPO + "@" + SAFE
        self.env["DRY_RUN"] = "false"
        self.assertEqual("NOT_DEPLOYED", self.run_worker()["status"])
        self.assertEqual([], self.mutations())

    def test_unrelated_pod_cannot_prove_digest_running(self):
        self.runner.bad_owner = True
        self.env["DRY_RUN"] = "false"
        self.assertEqual("FAILED", self.run_worker()["status"])
        self.assertEqual([], self.mutations())

    def test_failed_signature_or_scan_never_mutates(self):
        for command in ("cosign", "trivy"):
            with self.subTest(command=command):
                self.runner = Runner()
                self.runner.fail_command = command
                self.env["DRY_RUN"] = "false"
                self.assertEqual("FAILED", self.run_worker()["status"])
                self.assertEqual([], self.mutations())
                self.assertNotIn("SECRET_NEVER_LOG", self.output.getvalue())

    def test_concurrent_generation_change_prevents_overwrite(self):
        self.runner.race = True
        self.env["DRY_RUN"] = "false"
        self.assertEqual("FAILED", self.run_worker()["status"])
        self.assertEqual([], self.mutations())

    def test_rollout_failure_stops_without_rollback(self):
        self.runner.fail_command = "rollout"
        self.env["DRY_RUN"] = "false"
        result = self.run_worker()
        self.assertEqual("FAILED", result["status"])
        self.assertEqual("rollout_verification", result["failed_stage"])
        self.assertEqual(1, len(self.mutations()))
        self.assertFalse(any("undo" in args for args in self.runner.calls))

    def test_wrong_runtime_image_fails_post_verification(self):
        self.runner.verification_bad_digest = True
        self.env["DRY_RUN"] = "false"
        self.assertEqual("FAILED", self.run_worker()["status"])
        self.assertEqual(1, len(self.mutations()))

    def test_approval_change_stops_without_patch(self):
        self.runner.approval_digest = "sha256:" + "d" * 64
        self.env["DRY_RUN"] = "false"
        self.assertEqual("FAILED", self.run_worker()["status"])
        self.assertEqual([], self.mutations())

    def test_wrong_build_identity_refused_before_deployment_access(self):
        self.env["CODEBUILD_BUILD_ID"] = "another-project:build"
        with self.assertRaisesRegex(Rejected, "build_reservation_mismatch"):
            self.run_worker()
        self.assertEqual([], self.mutations())
        self.assertFalse(any(args[0] == "kubectl" for args in self.runner.calls))

    def test_gitops_managed_workload_requires_git_change(self):
        item = deployment()
        item["metadata"]["labels"] = {"argocd.argoproj.io/instance": "managed"}
        with self.assertRaisesRegex(Rejected, "gitops_workload"):
            deployment_patch(item, "test", REPO + "@" + BAD, REPO + "@" + SAFE)

    def test_terminating_old_pods_prevent_success_claim(self):
        new = pod(REPO + "@" + SAFE)
        old = pod()
        old["metadata"]["deletionTimestamp"] = NOW.isoformat()
        with self.assertRaisesRegex(Rejected, "terminating"):
            verify_running_pods(deployment(REPO + "@" + SAFE), RS, [new, old], "test", REPO + "@" + SAFE, after=True)

    def test_runtime_digest_without_repository_is_supported(self):
        item = pod(REPO + "@" + SAFE)
        item["status"]["containerStatuses"][0]["imageID"] = "containerd://" + SAFE
        self.assertEqual(1, verify_running_pods(deployment(REPO + "@" + SAFE), RS, [item], "test", REPO + "@" + SAFE, after=True))


class DeploymentVerificationTests(unittest.TestCase):
    def snapshots(self, wrong_target=None):
        targets = ["server", "client", "unauthorized"]
        deployments, replicasets, pods = {}, [], []
        for target in targets:
            image = REPO + "@" + (BAD if target == wrong_target else SAFE)
            item = deployment(image)
            item["metadata"].update(name=target, namespace="demo", uid=target + "-deployment")
            deployments[target] = item
            rs = copy.deepcopy(RS[0])
            rs["metadata"]["uid"] = target + "-rs"
            rs["metadata"]["ownerReferences"][0]["uid"] = target + "-deployment"
            replicasets.append(rs)
            item = pod(image)
            item["metadata"]["ownerReferences"][0]["uid"] = target + "-rs"
            item["spec"]["containers"][0]["env"] = [{"name": "NEVER_EXPORT", "value": "SECRET_SENTINEL"}]
            pods.append(item)
        def run(args, **kwargs):
            resource_index = args.index("get") + 1
            resource = args[resource_index]
            return json.dumps(deployments[args[resource_index + 1]] if resource == "deployment"
                              else {"items": replicasets if resource == "replicasets" else pods})
        return run

    def test_all_three_deployed_runtime_digests_required(self):
        result = verify_live_deployments("team4-eks", "demo", REPO + "@" + SAFE,
            ["server", "client", "unauthorized"], {}, self.snapshots(), timeout=0)
        self.assertEqual("VERIFIED", result["status"])
        self.assertEqual(3, len(result["deployments"]))
        self.assertNotIn("SECRET_SENTINEL", json.dumps(result))

    def test_one_wrong_runtime_digest_prevents_success(self):
        result = verify_live_deployments("team4-eks", "demo", REPO + "@" + SAFE,
            ["server", "client", "unauthorized"], {}, self.snapshots("client"), timeout=0)
        self.assertEqual("FAILED", result["status"])

    def test_duplicate_targets_rejected_before_api_reads(self):
        with self.assertRaisesRegex(Rejected, "deployment_targets_required"):
            verify_live_deployments("team4-eks", "demo", REPO + "@" + SAFE,
                ["server", "server"], {}, self.snapshots(), timeout=0)


if __name__ == "__main__":
    unittest.main()
