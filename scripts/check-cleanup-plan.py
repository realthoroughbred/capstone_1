#!/usr/bin/env python3
"""Check local Terraform JSON scope; never call AWS or execute a deletion.

This is a consistency check, not proof of cloud ownership or export completeness.
Use the ORIGINAL reviewed create-only plan, including its pre-apply prior_state.
Keep all inputs private: Terraform show JSON can contain plaintext secrets.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


AWS_PROVIDER = "registry.terraform.io/hashicorp/aws"
STATUS = "LOCAL_SCOPE_CHECK_PASSED"


class Rejected(ValueError):
    """Fixed diagnostic codes avoid leaking state values into output."""


def require(condition, code):
    if not condition:
        raise Rejected(code)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate_json_key")
        value[key] = item
    return value


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def inspect_saved_plan(path, expected, terraform_directory="infra"):
    """Read the actual binary locally, not a caller's unrelated JSON document."""
    binary = Path(path).resolve()
    before_hash = file_hash(binary)
    result = subprocess.run(["terraform", "-chdir=" + str(Path(terraform_directory).resolve()),
                             "show", "-json", str(binary)], capture_output=True, timeout=60, check=False)
    # Never emit Terraform stdout/stderr here: either can contain sensitive data.
    require(result.returncode == 0, "terraform_show_failed")
    actual = json.loads(result.stdout.decode("utf-8-sig"), object_pairs_hook=unique_object)
    require(file_hash(binary) == before_hash, "binary_plan_changed_during_read")
    require(fingerprint(actual) == fingerprint(expected), "binary_plan_json_mismatch")
    return actual, before_hash


def check_format(document):
    require(isinstance(document, dict) and str(document.get("format_version", "")).startswith("1."),
            "unsupported_terraform_json_format")


def state_resources(state):
    check_format(state)
    require(isinstance(state.get("values"), dict), "missing_state_values")
    result = {}

    def walk(module):
        require(isinstance(module, dict), "invalid_state_module")
        for resource in module.get("resources", []):
            require(resource.get("mode") in ("managed", "data"), "invalid_resource_mode")
            if resource["mode"] == "data":
                continue
            address = resource.get("address")
            require(isinstance(address, str) and bool(address), "missing_resource_address")
            require(address not in result, "duplicate_resource_address")
            result[address] = resource
        for child in module.get("child_modules", []):
            walk(child)

    walk(state["values"].get("root_module", {}))
    return result


def scope_from_plan(plan):
    check_format(plan)
    require(plan.get("errored") is not True and plan.get("complete") is not False,
            "incomplete_or_errored_plan")
    variables = plan.get("variables", {})
    scope = {key: variables.get(name, {}).get("value") for key, name in
             (("account", "aws_account_id"), ("region", "region"), ("project", "project"))}
    require(isinstance(scope["account"], str) and re.fullmatch(r"\d{12}", scope["account"]),
            "missing_or_invalid_plan_account")
    require(isinstance(scope["region"], str) and re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d+", scope["region"]),
            "missing_or_invalid_plan_region")
    require(isinstance(scope["project"], str) and re.fullmatch(r"[a-z][a-z0-9-]{2,19}", scope["project"]),
            "missing_or_invalid_plan_project")
    return scope


def managed_changes(plan):
    require(isinstance(plan.get("resource_changes"), list), "missing_plan_changes")
    seen = set()
    result = []
    for item in plan["resource_changes"]:
        require(item.get("mode") in ("managed", "data"), "invalid_change_mode")
        if item["mode"] == "data":
            continue
        address = item.get("address")
        require(isinstance(address, str) and address and address not in seen,
                "invalid_or_duplicate_change_address")
        seen.add(address)
        require(not item.get("previous_address") and not item.get("deposed"),
                "moved_or_deposed_resource_requires_review")
        require(not item.get("change", {}).get("importing"), "import_requires_separate_review")
        require(item.get("provider_name") == AWS_PROVIDER, "unexpected_managed_provider")
        result.append(item)
    return result


def approved_creates(plan, inventory=None):
    scope = scope_from_plan(plan)
    if "prior_state" not in plan:
        # Terraform 1.12.2 jsonplan.Marshal omits PriorState when State.Empty().
        # Do not assume that convention for unreviewed versions or infer cloud
        # absence from it. Also require the independently captured pre-apply
        # name inventory, and bind that evidence into the ledger.
        require(plan.get("terraform_version") == "1.12.2" and plan.get("format_version") == "1.2",
                "unverified_empty_prior_state_encoding")
        require(isinstance(inventory, dict) and inventory.get("read_only") is True
                and isinstance(inventory.get("timestamp"), str)
                and isinstance(inventory.get("checks"), list) and inventory["checks"],
                "pre_apply_inventory_required_for_omitted_prior_state")
        for item in inventory["checks"]:
            require(isinstance(item.get("name"), str)
                    and ((item.get("result") == "FOUND" and item.get("exit_code") == 0)
                         or (item.get("result") == "ABSENT" and item.get("exit_code") in (0, 254))),
                    "pre_apply_inventory_has_unresolved_check")
        prior = {}
    else:
        prior = state_resources(plan["prior_state"])
    # This project was approved as a wholly new deployment. An existing managed
    # resource in the original state is an unresolved ownership question.
    require(not prior, "preexisting_managed_state_requires_review")
    creates = {}
    for item in managed_changes(plan):
        change = item.get("change", {})
        require(change.get("actions") == ["create"] and change.get("before") is None,
                "approved_plan_must_only_create_new_resources")
        creates[item["address"]] = item["type"]
    require(bool(creates), "approved_plan_has_no_creates")
    return scope, creates


def identity(resource, scope):
    require(resource.get("provider_name") == AWS_PROVIDER, "unexpected_state_provider")
    values = resource.get("values", {})
    require(isinstance(values, dict), "invalid_resource_values")
    resource_id = values.get("id")
    require(isinstance(resource_id, str) and bool(resource_id), "resource_id_unknown")
    require(not resource.get("sensitive_values", {}).get("id"), "sensitive_id_requires_review")
    record = {"address": resource["address"], "type": resource["type"], "id": resource_id}
    if values.get("arn"):
        arn = values["arn"]
        require(isinstance(arn, str), "invalid_resource_arn")
        parts = arn.split(":", 5)
        require(len(parts) == 6 and parts[:2] == ["arn", "aws"], "invalid_resource_arn")
        require(parts[3] in ("", scope["region"]) and parts[4] in ("", scope["account"]),
                "resource_arn_scope_mismatch")
        record["arn"] = arn
    if values.get("region"):
        require(values["region"] == scope["region"], "resource_region_mismatch")
    for tag_key in ("tags", "tags_all"):
        tags = values.get(tag_key) or {}
        require(isinstance(tags, dict), "invalid_resource_tags")
        if "Project" in tags:
            require(tags["Project"] == scope["project"], "resource_project_tag_mismatch")
    if values.get("vpc_id"):
        record["vpc_id"] = values["vpc_id"]
    return record


def capture(plan, state, account, region, project, inventory=None):
    scope, creates = approved_creates(plan, inventory)
    require(scope == {"account": account, "region": region, "project": project},
            "requested_scope_differs_from_approved_plan")
    records = []
    for address, resource in state_resources(state).items():
        require(creates.get(address) == resource.get("type"), "state_contains_unapproved_resource")
        records.append(identity(resource, scope))
    require(bool(records), "no_created_resources_in_state")
    vpcs = {item["id"] for item in records if item["type"] == "aws_vpc"}
    for item in records:
        if "vpc_id" in item:
            require(item["vpc_id"] in vpcs, "resource_uses_untracked_vpc")
    return {"schema_version": 1, "status": "LOCAL_SCOPE_LEDGER_ONLY", "scope": scope,
            "approved_plan_sha256": fingerprint(plan), "captured_state_sha256": fingerprint(state),
            "pre_apply_inventory_sha256": fingerprint(inventory) if inventory is not None else None,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "resources": sorted(records, key=lambda item: item["address"]),
            "cloud_ownership_verified": False, "exports_verified": False,
            "cloud_mutations_executed": False}


def check(plan, ledger, destroy_plan, inventory=None):
    scope, creates = approved_creates(plan, inventory)
    require(ledger.get("schema_version") == 1 and ledger.get("status") == "LOCAL_SCOPE_LEDGER_ONLY",
            "invalid_ledger_schema")
    require(ledger.get("scope") == scope and ledger.get("approved_plan_sha256") == fingerprint(plan),
            "ledger_not_bound_to_approved_plan")
    require(ledger.get("pre_apply_inventory_sha256") ==
            (fingerprint(inventory) if inventory is not None else None), "pre_apply_inventory_changed")
    require(scope_from_plan(destroy_plan) == scope, "destroy_plan_scope_mismatch")
    known = {}
    for item in ledger.get("resources", []):
        address = item.get("address")
        require(address not in known and creates.get(address) == item.get("type"),
                "invalid_or_unapproved_ledger_resource")
        require(isinstance(item.get("id"), str) and bool(item["id"]), "invalid_ledger_id")
        known[address] = item
    require(bool(known), "empty_ledger")
    prior = state_resources(destroy_plan.get("prior_state", {}))
    for address, resource in prior.items():
        require(address in known and identity(resource, scope) == known[address],
                "destroy_state_identity_not_in_ledger")
    deletes, unchanged, seen = [], [], set()
    for item in managed_changes(destroy_plan):
        address = item["address"]
        require(address in prior and address in known, "destroy_change_not_in_tracked_state")
        require(item.get("type") == known[address]["type"], "destroy_resource_type_changed")
        change = item.get("change", {})
        action = change.get("actions")
        require(action in (["delete"], ["no-op"]), "destroy_plan_contains_non_delete_mutation")
        before = dict(prior[address], values=change.get("before"))
        require(identity(before, scope) == known[address], "destroy_before_identity_changed")
        if action == ["delete"]:
            require(change.get("after") is None, "delete_has_unexpected_after_values")
            deletes.append(known[address])
        else:
            require(change.get("before") == change.get("after"), "no_op_values_changed")
            unchanged.append(known[address])
        seen.add(address)
    require(seen == set(prior), "destroy_plan_omits_tracked_state_change")
    # A destroy plan can legitimately omit resources already removed in a prior
    # partial cleanup. That omission is NOT proof they no longer exist in AWS.
    return {"schema_version": 1, "status": STATUS, "scope": scope,
            "approved_plan_sha256": fingerprint(plan), "ledger_sha256": fingerprint(ledger),
            "destroy_plan_sha256": fingerprint(destroy_plan),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "delete_count": len(deletes), "unchanged_count": len(unchanged),
            "deletes": sorted(deletes, key=lambda item: item["address"]),
            "unchanged": sorted(unchanged, key=lambda item: item["address"]),
            "ledger_addresses_absent_from_plan": sorted(set(known) - seen),
            "cloud_ownership_verified": False, "exports_verified": False,
            "cleanup_complete": False, "cloud_mutations_executed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("capture", help="Create a local ID ledger after successful or partial apply")
    make.add_argument("--approved-plan", required=True)
    make.add_argument("--current-state", required=True, help="terraform show -json state, not raw state pull")
    make.add_argument("--pre-apply-inventory", help="Original read-only name inventory, mandatory if prior_state omitted")
    for name in ("account", "region", "project", "output"):
        make.add_argument("--" + name, required=True)
    verify = sub.add_parser("check", help="Reject a destroy plan outside the exact recorded new IDs")
    for name in ("approved-plan", "ledger", "destroy-plan", "destroy-plan-file", "output"):
        verify.add_argument("--" + name, required=True)
    verify.add_argument("--pre-apply-inventory", help="Same original inventory used during capture")
    verify.add_argument("--terraform-directory", default="infra", help="Initialized directory for local terraform show")
    args = parser.parse_args(argv)
    try:
        inputs = [args.approved_plan]
        if args.command == "capture":
            inputs.append(args.current_state)
        else:
            inputs.extend((args.ledger, args.destroy_plan, args.destroy_plan_file))
        if args.pre_apply_inventory:
            inputs.append(args.pre_apply_inventory)
        require(Path(args.output).resolve() not in {Path(item).resolve() for item in inputs},
                "output_would_overwrite_input")
        # Never replace an earlier audit record silently. Use a new filename for
        # each partial deployment/cleanup stage.
        require(not Path(args.output).exists(), "output_already_exists")
        plan = read_json(args.approved_plan)
        inventory = read_json(args.pre_apply_inventory) if args.pre_apply_inventory else None
        if args.command == "capture":
            result = capture(plan, read_json(args.current_state), args.account, args.region, args.project, inventory)
        else:
            actual, binary_hash = inspect_saved_plan(args.destroy_plan_file, read_json(args.destroy_plan),
                                                     args.terraform_directory)
            result = check(plan, read_json(args.ledger), actual, inventory)
            require(file_hash(args.destroy_plan_file) == binary_hash, "binary_plan_changed_during_check")
            result["destroy_plan_file_sha256"] = binary_hash
            result["binary_plan_json_verified"] = True
        with Path(args.output).open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({"status": result["status"], "resources": len(result.get("resources", [])),
                          "delete_count": result.get("delete_count", 0), "cloud_mutations_executed": False}))
        return 0
    except Rejected as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}), file=sys.stderr)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        print(json.dumps({"status": "REJECTED", "reason": "invalid_or_unreadable_local_input"}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
