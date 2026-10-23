"""Offline Inspector/CodeBuild safety tests, using simulated findings only."""

import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from automation.common import Rejected
from automation.inspector_response import respond


ACCOUNT = "123456789012"
REGION = "ap-northeast-2"
BAD = "sha256:" + "a" * 64
SAFE = "sha256:" + "b" * 64
NOW = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
ARN = f"arn:aws:inspector2:{REGION}:{ACCOUNT}:finding/simulated-finding"
FINDING = {"awsAccountId": ACCOUNT, "findingArn": ARN, "status": "ACTIVE", "severity": "CRITICAL",
           "type": "PACKAGE_VULNERABILITY", "resources": [{
               "type": "AWS_ECR_CONTAINER_IMAGE", "region": REGION, "partition": "aws",
               "id": f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/team4-test/{BAD}",
               "details": {"awsEcrContainerImage": {"registry": ACCOUNT,
                                                     "repositoryName": "team4-test", "imageHash": BAD}}}]}
EVENT = {"_evidence_kind": "SIMULATED_FIXTURE", "id": "simulated-event",
         "source": "aws.inspector2", "detail-type": "Inspector2 Finding",
         "account": ACCOUNT, "region": REGION, "time": NOW.isoformat(), "detail": FINDING}
ENV = {"EXPECTED_ACCOUNT_ID": ACCOUNT, "EXPECTED_REGION": REGION, "PROJECT": "team4",
       "ECR_REPOSITORY": "team4-test", "CLUSTER_NAME": "team4-eks", "DEPLOY_NAMESPACE": "demo",
       "DEPLOYMENT": "server", "DEPLOY_CONTAINER": "test", "APPROVED_IMAGE_PARAMETER": "/team4/approved-image",
       "CODEBUILD_PROJECT": "team4-remediate", "IDEMPOTENCY_TABLE": "team4-remediation"}
ENV.update(REMEDIATION_SOURCE_REVISION="c" * 40,
           REMEDIATION_SOURCE_URL="https://github.com/realthoroughbred/capstone_1.git",
           CODEBUILD_SERVICE_ROLE_ARN=f"arn:aws:iam::{ACCOUNT}:role/team4-remediate",
           SIGNING_IDENTITY="https://github.com/realthoroughbred/capstone_1/.github/workflows/deploy.yml@refs/heads/main",
           SIGNING_ISSUER="https://token.actions.githubusercontent.com")


class ApiError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.event = copy.deepcopy(EVENT)
        self.env = dict(ENV)
        self.clients = {name: Mock() for name in ("sts", "inspector2", "ssm", "ecr", "dynamodb", "codebuild")}
        self.clients["sts"].get_caller_identity.return_value = {"Account": ACCOUNT}
        self.clients["inspector2"].list_findings.return_value = {"findings": [copy.deepcopy(FINDING)]}
        self.approval = {"approved": True, "repository": "team4-test", "digest": SAFE,
                         "expires_at": "2026-10-18T01:00:00Z"}
        self.set_approval()
        self.clients["ecr"].describe_images.return_value = {"imageDetails": [
            {"imageDigest": SAFE, "imageManifestMediaType": "application/vnd.oci.image.manifest.v1+json"}]}
        self.clients["ecr"].describe_image_scan_findings.return_value = {
            "registryId": ACCOUNT, "repositoryName": "team4-test", "imageId": {"imageDigest": SAFE},
            "imageScanStatus": {"status": "ACTIVE"},
            "imageScanFindings": {"imageScanCompletedAt": NOW, "findingSeverityCounts": {}}}
        self.clients["codebuild"].start_build.return_value = {"build": {"id": "team4-remediate:example-build"}}
        self.clients["codebuild"].batch_get_projects.side_effect = lambda **kwargs: {"projects": [{
            "name": "team4-remediate", "arn": f"arn:aws:codebuild:{REGION}:{ACCOUNT}:project/team4-remediate",
            "sourceVersion": self.env["REMEDIATION_SOURCE_REVISION"],
            "serviceRole": self.env["CODEBUILD_SERVICE_ROLE_ARN"],
            "source": {"type": "GITHUB", "location": self.env["REMEDIATION_SOURCE_URL"],
                       "buildspec": "automation/buildspec-remediate.yml"},
            "environment": {"privilegedMode": False, "environmentVariables": [
                {"name": key, "value": value, "type": "PLAINTEXT"}
                for key, value in dict(self.env, DRY_RUN=self.env.get("DRY_RUN", "true")).items()]}}]}

    def set_approval(self):
        self.clients["ssm"].get_parameter.return_value = {"Parameter": {"Value": json.dumps(self.approval)}}

    def run_response(self):
        return respond(self.event, self.env, self.clients, NOW)

    def assert_no_mutation(self):
        self.clients["codebuild"].start_build.assert_not_called()
        self.clients["dynamodb"].put_item.assert_not_called()

    def test_default_dry_run_validates_without_writes(self):
        result = self.run_response()
        self.assertEqual("DRY_RUN", result["status"])
        self.assertEqual("SIMULATED_EVENT", result["event_origin"])
        self.assert_no_mutation()

    def test_valid_finding_starts_bounded_build_with_only_three_overrides(self):
        self.env["DRY_RUN"] = "false"
        result = self.run_response()
        self.assertEqual("BUILD_STARTED", result["status"])
        self.assertEqual("NOT_EXECUTED", result["verification"])
        request = self.clients["codebuild"].start_build.call_args.kwargs
        self.assertEqual(15, request["timeoutInMinutesOverride"])
        self.assertEqual(5, request["queuedTimeoutInMinutesOverride"])
        self.assertEqual("c" * 40, request["sourceVersion"])
        self.assertEqual({"BAD_DIGEST", "SAFE_DIGEST", "REMEDIATION_ID"},
                         {v["name"] for v in request["environmentVariablesOverride"]})
        self.assertEqual(64, len(request["idempotencyToken"]))
        reserved = self.clients["dynamodb"].put_item.call_args.kwargs
        self.assertEqual("attribute_not_exists(id)", reserved["ConditionExpression"])
        self.assertNotIn("expires_at", reserved["Item"])

    def test_changed_event_id_and_finding_id_cannot_bypass_dedup(self):
        first = self.run_response()["remediation_id"]
        self.event["id"] = "different-event"
        self.event["detail"]["findingArn"] = ARN + "2"
        self.clients["inspector2"].list_findings.return_value["findings"][0]["findingArn"] = ARN + "2"
        self.assertEqual(first, self.run_response()["remediation_id"])

    def test_duplicate_started_build_is_not_restarted(self):
        self.env["DRY_RUN"] = "false"
        self.clients["dynamodb"].put_item.side_effect = ApiError("ConditionalCheckFailedException")
        self.clients["dynamodb"].get_item.return_value = {"Item": {"status": {"S": "BUILD_STARTED"}}}
        self.assertEqual("DUPLICATE", self.run_response()["status"])
        self.clients["codebuild"].start_build.assert_not_called()

    def test_uncertain_prior_start_requires_manual_review(self):
        self.env["DRY_RUN"] = "false"
        self.clients["dynamodb"].put_item.side_effect = ApiError("ConditionalCheckFailedException")
        self.clients["dynamodb"].get_item.return_value = {"Item": {"status": {"S": "RESERVED"}}}
        with self.assertRaisesRegex(RuntimeError, "manual_review"):
            self.run_response()
        self.clients["codebuild"].start_build.assert_not_called()

    def test_start_failure_keeps_reservation_and_does_not_retry_blindly(self):
        self.env["DRY_RUN"] = "false"
        self.clients["codebuild"].start_build.side_effect = TimeoutError("must never be logged")
        with self.assertRaisesRegex(RuntimeError, "manual_review"):
            self.run_response()
        self.clients["dynamodb"].delete_item.assert_not_called()

    def test_wrong_event_scope_rejected(self):
        for key, value in (("account", "999999999999"), ("region", "us-east-1"), ("source", "example.synthetic")):
            with self.subTest(key=key):
                self.event = dict(EVENT, **{key: value})
                with self.assertRaises(Rejected):
                    self.run_response()
                self.assert_no_mutation()

    def test_low_severity_or_closed_event_ignored(self):
        for change in ({"severity": "MEDIUM"}, {"status": "CLOSED"}, {"status": "SUPPRESSED"}):
            self.event = copy.deepcopy(EVENT)
            self.event["detail"].update(change)
            self.assertEqual("IGNORED", self.run_response()["status"])
            self.assert_no_mutation()

    def test_event_requires_current_authoritative_finding(self):
        self.clients["inspector2"].list_findings.return_value = {"findings": []}
        with self.assertRaisesRegex(Rejected, "authoritative_finding_missing"):
            self.run_response()
        self.assert_no_mutation()

    def test_authoritative_closed_finding_rejected(self):
        self.clients["inspector2"].list_findings.return_value["findings"][0]["status"] = "CLOSED"
        with self.assertRaisesRegex(Rejected, "not_active"):
            self.run_response()
        self.assert_no_mutation()

    def test_wrong_repository_or_digest_rejected(self):
        for field, value in (("repositoryName", "production"), ("registry", "999999999999"),
                             ("imageHash", "latest")):
            self.event = copy.deepcopy(EVENT)
            self.event["detail"]["resources"][0]["details"]["awsEcrContainerImage"][field] = value
            with self.assertRaises(Rejected):
                self.run_response()
            self.assert_no_mutation()

    def test_no_safe_approval_means_no_rollback(self):
        for change in ({"approved": False}, {"digest": BAD}, {"expires_at": "2026-10-17T00:00:00Z"},
                       {"repository": "production"}, {"expires_at": "2030-01-01T00:00:00Z"}):
            with self.subTest(change=change):
                original = copy.deepcopy(self.approval)
                self.approval.update(change)
                self.set_approval()
                with self.assertRaises(Rejected):
                    self.run_response()
                self.assert_no_mutation()
                self.approval = original

    def test_vulnerable_or_incomplete_replacement_scan_rejected(self):
        scan = self.clients["ecr"].describe_image_scan_findings.return_value
        scan["imageScanFindings"]["findingSeverityCounts"] = {"HIGH": 1}
        with self.assertRaisesRegex(Rejected, "is_vulnerable"):
            self.run_response()
        scan["imageScanFindings"]["findingSeverityCounts"] = {}
        scan["imageScanStatus"]["status"] = "PENDING"
        with self.assertRaisesRegex(Rejected, "not_ready"):
            self.run_response()
        self.assert_no_mutation()

    def test_stale_event_rejected(self):
        self.event["time"] = "2026-10-01T00:00:00Z"
        with self.assertRaisesRegex(Rejected, "stale_or_future"):
            self.run_response()

    def test_multi_arch_replacement_requires_manual_review(self):
        self.clients["ecr"].describe_images.return_value["imageDetails"][0]["imageManifestMediaType"] = (
            "application/vnd.oci.image.index.v1+json")
        with self.assertRaisesRegex(Rejected, "multi_arch"):
            self.run_response()
        self.assert_no_mutation()

    def test_dedup_outage_prevents_start(self):
        self.env["DRY_RUN"] = "false"
        self.clients["dynamodb"].put_item.side_effect = ApiError("AccessDeniedException")
        with self.assertRaisesRegex(RuntimeError, "deduplication_unavailable"):
            self.run_response()
        self.clients["codebuild"].start_build.assert_not_called()

    def test_wrong_external_build_source_rejected(self):
        project = self.clients["codebuild"].batch_get_projects()["projects"][0]
        project["sourceVersion"] = "d" * 40
        self.clients["codebuild"].batch_get_projects.side_effect = None
        self.clients["codebuild"].batch_get_projects.return_value = {"projects": [project]}
        with self.assertRaisesRegex(Rejected, "build_source_mismatch"):
            self.run_response()
        self.assert_no_mutation()

    def test_wrong_external_build_environment_rejected(self):
        project = self.clients["codebuild"].batch_get_projects()["projects"][0]
        project["environment"]["environmentVariables"] = []
        self.clients["codebuild"].batch_get_projects.side_effect = None
        self.clients["codebuild"].batch_get_projects.return_value = {"projects": [project]}
        with self.assertRaisesRegex(Rejected, "build_environment_mismatch"):
            self.run_response()
        self.assert_no_mutation()


if __name__ == "__main__":
    unittest.main()
