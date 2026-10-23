"""Synthetic local plans only; no AWS SDK, credentials, or network access."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location(
    "cleanup_plan", Path(__file__).resolve().parents[1] / "scripts" / "check-cleanup-plan.py")
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)

ACCOUNT, REGION, PROJECT = "123456789012", "ap-northeast-2", "team4"
VPC, SG = "aws_vpc.demo", "aws_security_group.healing_demo"


def resource(address, resource_type, resource_id, **values):
    return {"address": address, "mode": "managed", "type": resource_type,
            "provider_name": cleanup.AWS_PROVIDER,
            "values": {"id": resource_id, "tags_all": {"Project": PROJECT}, **values},
            "sensitive_values": {}}


def state(resources):
    return {"format_version": "1.0", "values": {"root_module": {"resources": resources}}}


def plan(resources, action="create"):
    result = {"format_version": "1.2", "complete": True, "errored": False,
              "variables": {name: {"value": value} for name, value in
                            (("aws_account_id", ACCOUNT), ("region", REGION), ("project", PROJECT))},
              "prior_state": state([] if action == "create" else copy.deepcopy(resources)),
              "resource_changes": []}
    for item in resources:
        change = {key: item[key] for key in ("address", "type", "mode", "provider_name")}
        change["change"] = {"actions": [action],
                            "before": None if action == "create" else copy.deepcopy(item["values"]),
                            "after": None if action == "delete" else copy.deepcopy(item["values"])}
        result["resource_changes"].append(change)
    return result


class CleanupScopeTests(unittest.TestCase):
    def setUp(self):
        self.resources = [resource(VPC, "aws_vpc", "vpc-new"),
                          resource(SG, "aws_security_group", "sg-new", vpc_id="vpc-new",
                                   arn=f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/sg-new")]
        self.approved = plan(self.resources)
        self.ledger = cleanup.capture(self.approved, state(self.resources), ACCOUNT, REGION, PROJECT)

    def test_complete_new_deployment_exact_destroy_is_local_check_only(self):
        result = cleanup.check(self.approved, self.ledger, plan(self.resources, "delete"))
        self.assertEqual(result["delete_count"], 2)
        self.assertFalse(result["cloud_mutations_executed"])
        self.assertFalse(result["cloud_ownership_verified"])
        self.assertFalse(result["cleanup_complete"])

    def test_partial_apply_captures_only_created_subset(self):
        ledger = cleanup.capture(self.approved, state(self.resources[:1]), ACCOUNT, REGION, PROJECT)
        result = cleanup.check(self.approved, ledger, plan(self.resources[:1], "delete"))
        self.assertEqual(result["delete_count"], 1)

    def test_partial_cleanup_absence_is_not_claimed_as_cloud_deletion(self):
        result = cleanup.check(self.approved, self.ledger, plan(self.resources[:1], "delete"))
        self.assertEqual(result["ledger_addresses_absent_from_plan"], [SG])
        self.assertFalse(result["cleanup_complete"])

    def test_nested_modules_and_data_sources_are_handled(self):
        nested = copy.deepcopy(self.resources[0])
        nested["address"] = "module.demo." + VPC
        value = state([{"address": "data.aws_secret.example", "mode": "data"}])
        value["values"]["root_module"]["child_modules"] = [{"resources": [nested]}]
        ledger = cleanup.capture(plan([nested]), value, ACCOUNT, REGION, PROJECT)
        self.assertEqual(len(ledger["resources"]), 1)

    def test_original_plan_with_existing_managed_state_is_rejected(self):
        self.approved["prior_state"] = state(self.resources[:1])
        with self.assertRaisesRegex(cleanup.Rejected, "preexisting_managed"):
            cleanup.capture(self.approved, state(self.resources), ACCOUNT, REGION, PROJECT)

    def test_capture_refuses_foreign_resource_and_untracked_parent_vpc(self):
        foreign = resource("aws_vpc.existing", "aws_vpc", "vpc-existing")
        with self.assertRaisesRegex(cleanup.Rejected, "unapproved_resource"):
            cleanup.capture(self.approved, state([*self.resources, foreign]), ACCOUNT, REGION, PROJECT)
        self.resources[1]["values"]["vpc_id"] = "vpc-existing"
        with self.assertRaisesRegex(cleanup.Rejected, "untracked_vpc"):
            cleanup.capture(self.approved, state(self.resources), ACCOUNT, REGION, PROJECT)

    def test_changed_id_or_arn_blocks_destroy(self):
        for field, value in (("id", "sg-replacement"),
                             ("arn", f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/sg-other")):
            changed = copy.deepcopy(self.resources)
            changed[1]["values"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(cleanup.Rejected, "identity_not_in_ledger"):
                cleanup.check(self.approved, self.ledger, plan(changed, "delete"))

    def test_wrong_account_region_or_project_is_rejected(self):
        for field, value in (("aws_account_id", "999999999999"), ("region", "us-east-1"), ("project", "other")):
            destroy = plan(self.resources, "delete")
            destroy["variables"][field]["value"] = value
            with self.subTest(field=field), self.assertRaisesRegex(cleanup.Rejected, "scope_mismatch"):
                cleanup.check(self.approved, self.ledger, destroy)
        foreign = copy.deepcopy(self.resources)
        foreign[1]["values"]["arn"] = f"arn:aws:ec2:{REGION}:999999999999:security-group/sg-new"
        with self.assertRaisesRegex(cleanup.Rejected, "arn_scope_mismatch"):
            cleanup.capture(self.approved, state(foreign), ACCOUNT, REGION, PROJECT)

    def test_update_replace_create_forget_or_import_is_rejected(self):
        for actions in (["update"], ["delete", "create"], ["create", "delete"], ["create"], ["forget"]):
            destroy = plan(self.resources, "delete")
            destroy["resource_changes"][0]["change"]["actions"] = actions
            with self.subTest(actions=actions), self.assertRaisesRegex(cleanup.Rejected, "non_delete_mutation"):
                cleanup.check(self.approved, self.ledger, destroy)
        destroy = plan(self.resources, "delete")
        destroy["resource_changes"][0]["change"]["importing"] = {"id": "vpc-existing"}
        with self.assertRaisesRegex(cleanup.Rejected, "import_requires"):
            cleanup.check(self.approved, self.ledger, destroy)

    def test_noop_for_existing_or_untracked_resource_is_rejected(self):
        destroy = plan(self.resources, "delete")
        foreign = resource("aws_vpc.existing", "aws_vpc", "vpc-existing")
        destroy["prior_state"]["values"]["root_module"]["resources"].append(foreign)
        destroy["resource_changes"].extend(plan([foreign], "no-op")["resource_changes"])
        with self.assertRaisesRegex(cleanup.Rejected, "identity_not_in_ledger"):
            cleanup.check(self.approved, self.ledger, destroy)

    def test_incomplete_plan_moved_deposed_or_omitted_change_is_rejected(self):
        cases = []
        partial = plan(self.resources, "delete")
        partial["complete"] = False
        cases.append(partial)
        for field in ("previous_address", "deposed"):
            changed = plan(self.resources, "delete")
            changed["resource_changes"][0][field] = "unreviewed"
            cases.append(changed)
        omitted = plan(self.resources, "delete")
        omitted["resource_changes"].pop()
        cases.append(omitted)
        for item in cases:
            with self.subTest(plan=item), self.assertRaises(cleanup.Rejected):
                cleanup.check(self.approved, self.ledger, item)

    def test_changed_approved_plan_cannot_reuse_ledger(self):
        self.approved["variables"]["new_setting"] = {"value": True}
        with self.assertRaisesRegex(cleanup.Rejected, "not_bound_to_approved_plan"):
            cleanup.check(self.approved, self.ledger, plan(self.resources, "delete"))

    def test_known_empty_prior_state_encoding_needs_independent_inventory(self):
        self.approved.pop("prior_state")
        self.approved["terraform_version"] = "1.12.2"
        inventory = {"read_only": True, "timestamp": "2026-10-18T00:00:00Z", "checks": [
            {"name": "demo_name", "exit_code": 254, "result": "ABSENT"}]}
        with self.assertRaisesRegex(cleanup.Rejected, "pre_apply_inventory_required"):
            cleanup.capture(self.approved, state(self.resources), ACCOUNT, REGION, PROJECT)
        ledger = cleanup.capture(self.approved, state(self.resources), ACCOUNT, REGION, PROJECT, inventory)
        result = cleanup.check(self.approved, ledger, plan(self.resources, "delete"), inventory)
        self.assertEqual(result["delete_count"], 2)
        changed = copy.deepcopy(inventory)
        changed["timestamp"] = "2026-10-18T01:00:00Z"
        with self.assertRaisesRegex(cleanup.Rejected, "inventory_changed"):
            cleanup.check(self.approved, ledger, plan(self.resources, "delete"), changed)

    def test_unknown_empty_state_encoding_or_failed_inventory_is_rejected(self):
        self.approved.pop("prior_state")
        self.approved["terraform_version"] = "1.99.0"
        with self.assertRaisesRegex(cleanup.Rejected, "unverified_empty_prior_state"):
            cleanup.capture(self.approved, state(self.resources), ACCOUNT, REGION, PROJECT)
        self.approved["terraform_version"] = "1.12.2"
        inventory = {"read_only": True, "timestamp": "2026-10-18T00:00:00Z", "checks": [
            {"name": "demo_name", "exit_code": 254, "result": "ACCESS_DENIED"}]}
        with self.assertRaisesRegex(cleanup.Rejected, "unresolved_check"):
            cleanup.capture(self.approved, state(self.resources), ACCOUNT, REGION, PROJECT, inventory)

    def test_actual_binary_is_read_locally_and_bound_to_json(self):
        destroy = plan(self.resources, "delete")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "destroy.tfplan"
            binary.write_bytes(b"SYNTHETIC_BINARY_NOT_A_TERRAFORM_FILE")
            with patch.object(cleanup.subprocess, "run", return_value=Mock(
                    returncode=0, stdout=json.dumps(destroy).encode())) as run:
                actual, digest = cleanup.inspect_saved_plan(binary, destroy, directory)
            self.assertEqual(actual, destroy)
            self.assertEqual(digest, cleanup.file_hash(binary))
            self.assertEqual(run.call_args.args[0], ["terraform", "-chdir=" + str(Path(directory).resolve()),
                                                    "show", "-json", str(binary.resolve())])

    def test_safe_json_with_different_binary_cannot_pass(self):
        safe, unsafe = plan(self.resources, "delete"), plan(self.resources, "create")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "other.tfplan"
            binary.write_bytes(b"SYNTHETIC_OTHER_BINARY")
            with patch.object(cleanup.subprocess, "run", return_value=Mock(
                    returncode=0, stdout=json.dumps(unsafe).encode())):
                with self.assertRaisesRegex(cleanup.Rejected, "binary_plan_json_mismatch"):
                    cleanup.inspect_saved_plan(binary, safe, directory)

    def test_binary_changed_during_show_and_failed_show_are_rejected(self):
        destroy = plan(self.resources, "delete")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "destroy.tfplan"
            binary.write_bytes(b"SYNTHETIC_INITIAL")

            def replace_during_show(*args, **kwargs):
                binary.write_bytes(b"SYNTHETIC_CHANGED")
                return Mock(returncode=0, stdout=json.dumps(destroy).encode())

            with patch.object(cleanup.subprocess, "run", side_effect=replace_during_show):
                with self.assertRaisesRegex(cleanup.Rejected, "binary_plan_changed_during_read"):
                    cleanup.inspect_saved_plan(binary, destroy, directory)
            with patch.object(cleanup.subprocess, "run", return_value=Mock(
                    returncode=1, stdout=b"secret value must not be printed", stderr=b"secret")):
                with self.assertRaisesRegex(cleanup.Rejected, "terraform_show_failed"):
                    cleanup.inspect_saved_plan(binary, destroy, directory)

    def test_secrets_in_state_are_not_exported(self):
        secret = "THIS_IS_A_SYNTHETIC_SECRET_VALUE"
        self.resources[0]["values"]["private_key"] = secret
        result = cleanup.capture(self.approved, state(self.resources), ACCOUNT, REGION, PROJECT)
        self.assertNotIn(secret, json.dumps(result))

    def test_duplicate_json_keys_and_output_overwrite_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"id": "first", "id": "second"}', encoding="utf-8")
            with self.assertRaisesRegex(cleanup.Rejected, "duplicate_json_key"):
                cleanup.read_json(duplicate)
            plan_path, state_path = root / "plan.json", root / "state.json"
            plan_path.write_text(json.dumps(self.approved), encoding="utf-8")
            state_path.write_text(json.dumps(state(self.resources)), encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as error:
                code = cleanup.main(["capture", "--approved-plan", str(plan_path),
                                     "--current-state", str(state_path), "--account", ACCOUNT,
                                     "--region", REGION, "--project", PROJECT, "--output", str(state_path)])
            self.assertEqual(code, 2)
            self.assertIn("output_would_overwrite_input", error.getvalue())


if __name__ == "__main__":
    unittest.main()
