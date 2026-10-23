#!/usr/bin/env python3
"""Render reviewed bootstrap documents locally; never contacts AWS or runs commands."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = "852093844554"
REGION = "ap-northeast-2"
PROJECT = "team4"
CLUSTER = "team4-eks"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def policy(name: str):
    return read_json(ROOT / "iam" / name)


def resource_id(value: str | None, prefix: str) -> str:
    if not value or not re.fullmatch(rf"{prefix}-[0-9a-f]{{8}}(?:[0-9a-f]{{9}})?", value):
        raise ValueError(f"Supply the observed new {prefix} resource ID, without wildcards.")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--phase", choices=["initial", "network", "cluster"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--vpc-id")
    parser.add_argument("--default-sg-id")
    parser.add_argument("--subnet-a-id")
    parser.add_argument("--subnet-c-id")
    parser.add_argument("--node-sg-id")
    parser.add_argument("--issuer-url")
    parser.add_argument("--new-github-provider-confirmed", action="store_true",
                        help="Only after inventory proves the GitHub provider is absent.")
    args = parser.parse_args()
    plan = read_json(args.plan)
    variables = {name: item["value"] for name, item in plan["variables"].items()}
    for name, expected in [("aws_account_id", ACCOUNT), ("region", REGION),
                           ("project", PROJECT), ("cluster_name", CLUSTER)]:
        if variables.get(name) != expected:
            raise ValueError(f"Saved plan {name} does not match this reviewed project.")
    if variables.get("enable_inspector_response"):
        raise ValueError("This bootstrap is for the approved 67-resource baseline, not Inspector/CodeBuild.")
    changes = plan.get("resource_changes", [])
    if any(item.get("mode") == "managed" and item["change"]["actions"] not in (["create"], ["no-op"])
           for item in changes):
        raise ValueError("Use the reviewed original creation plan; do not generate from an update/destroy plan.")
    destination = args.out.resolve()
    if not destination.is_relative_to((ROOT / "generated").resolve()):
        raise ValueError("Output must stay below this repository's ignored generated/ directory.")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Output directory must be empty; preserve previous reviewed documents.")
    destination.mkdir(parents=True, exist_ok=True)
    documents = {}

    boundary = policy("team4-runtime-boundary.json")
    # The documented EKS minimum for a cluster with no LoadBalancer service.
    # AWS service-linked roles handle control-plane interfaces separately.
    boundary["Statement"].append({
        "Sid": "EKSOwnNodeClusterTagOnly", "Effect": "Allow", "Action": "ec2:CreateTags",
        "Resource": f"arn:aws:ec2:{REGION}:{ACCOUNT}:instance/*",
        "Condition": {
            "ArnEquals": {"aws:PrincipalArn": f"arn:aws:iam::{ACCOUNT}:role/team4-eks-cluster"},
            "StringEquals": {"ec2:ResourceTag/Project": PROJECT},
            "ForAllValues:StringEquals": {"aws:TagKeys": [f"kubernetes.io/cluster/{CLUSTER}"]},
        },
    })

    if args.phase == "initial":
        key_change = next(item for item in changes if item["address"] == "aws_kms_key.project")
        after = key_change["change"]["after"]
        key_policy = json.loads(after["policy"])
        documents["kms-create-key.json"] = {
            "Description": after["description"], "KeyUsage": "ENCRYPT_DECRYPT",
            "KeySpec": "SYMMETRIC_DEFAULT", "Origin": "AWS_KMS", "MultiRegion": False,
            "Policy": json.dumps(key_policy, separators=(",", ":")),
            "Tags": [{"TagKey": key, "TagValue": value} for key, value in after["tags_all"].items()],
        }
        documents["operator-provisioning.json"] = policy("team4-operator-provisioning.json")
        documents["operator-demo-validation.json"] = policy("team4-operator-demo-validation.json")
        optional = policy("team4-operator-optional-automation.json")
        config_only = copy.deepcopy(optional["Statement"][0])
        config_only["Action"] = [action for action in config_only["Action"] if action.startswith("config:")]
        config_only["Sid"] = "ApprovedNewRegionalConfigRecorder"
        documents["operator-config-only.json"] = {"Version": "2012-10-17", "Statement": [config_only]}
        bucket = f"arn:aws:s3:::team4-{ACCOUNT}-{REGION}-evidence"
        documents["operator-evidence-session.json"] = {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:DeleteObject", "s3:DeleteObjectVersion"], "Resource": f"{bucket}/*"},
            {"Effect": "Allow", "Action": "s3:ListBucketVersions", "Resource": bucket},
            {"Effect": "Allow", "Action": ["config:GetComplianceDetailsByConfigRule", "config:StartConfigRulesEvaluation"],
             "Resource": f"arn:aws:config:{REGION}:{ACCOUNT}:config-rule/*",
             "Condition": {"StringEquals": {"aws:ResourceTag/Project": PROJECT}}},
        ]}
        if args.new_github_provider_confirmed:
            if variables.get("existing_github_oidc_provider_arn"):
                raise ValueError("Plan reuses an existing GitHub provider; do not grant modification rights.")
            documents["operator-new-github-provider.json"] = {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Action": ["iam:CreateOpenIDConnectProvider", "iam:DeleteOpenIDConnectProvider",
                    "iam:TagOpenIDConnectProvider", "iam:UntagOpenIDConnectProvider", "iam:UpdateOpenIDConnectProviderThumbprint"],
                "Resource": f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com",
            }]}
    else:
        vpc = resource_id(args.vpc_id, "vpc")
        # The original account inventory contains this existing default VPC.
        if vpc == "vpc-044ea157cc2bf6edc":
            raise ValueError("The existing default VPC is excluded from this experiment.")
        default_sg = resource_id(args.default_sg_id, "sg")
        bootstrap = policy("team4-operator-bootstrap.template.json")
        bootstrap["Statement"][0]["Resource"] = f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/{default_sg}"
        if args.phase == "network":
            bootstrap["Statement"] = bootstrap["Statement"][:1]
        else:
            subnet_a = resource_id(args.subnet_a_id, "subnet")
            subnet_c = resource_id(args.subnet_c_id, "subnet")
            node_sg = resource_id(args.node_sg_id, "sg")
            if subnet_a == subnet_c or node_sg == default_sg:
                raise ValueError("Expected two distinct subnets and the new EKS cluster security group.")
            if not args.issuer_url or not re.fullmatch(rf"https://oidc\.eks\.{REGION}\.amazonaws\.com/id/[A-Fa-f0-9]{{32}}", args.issuer_url):
                raise ValueError("Supply the exact observed EKS OIDC issuer URL.")
            replacements = {
                "REPLACE_APPROVED_VPC_ID": vpc, "REPLACE_APPROVED_SUBNET_A_ID": subnet_a,
                "REPLACE_APPROVED_SUBNET_C_ID": subnet_c, "REPLACE_APPROVED_NODE_SECURITY_GROUP_ID": node_sg,
            }
            fragment_text = json.dumps(policy("team4-runtime-network-boundary-fragment.json"))
            for placeholder, value in replacements.items():
                fragment_text = fragment_text.replace(placeholder, value)
            boundary["Statement"].extend(json.loads(fragment_text)["Statement"])
            bootstrap["Statement"][1]["Resource"] = f"arn:aws:iam::{ACCOUNT}:oidc-provider/{args.issuer_url.removeprefix('https://')}"
        # Terraform reads DNS attributes after creating the VPC. Keep this
        # recovery grant bound to the observed new VPC, including cluster phase.
        bootstrap["Statement"].append({
            "Sid": "OnlyNewProjectVPCAttributes", "Effect": "Allow",
            "Action": "ec2:DescribeVpcAttribute",
            "Resource": f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/{vpc}",
        })
        documents["operator-new-resource-bootstrap.json"] = bootstrap

    # Statement labels are optional. Remove only labels to fit the IAM size limit;
    # keep every permission and condition unchanged, and retain source labels below.
    source_labels = [statement.get("Sid") for statement in boundary["Statement"]]
    for statement in boundary["Statement"]:
        statement.pop("Sid", None)
    documents["runtime-boundary.json"] = boundary
    manifest = {"aws_calls": False, "phase": args.phase,
                "plan_json_sha256": hashlib.sha256(args.plan.read_bytes()).hexdigest(),
                "boundary_source_statement_labels": source_labels, "files": {}}
    for name, document in documents.items():
        encoded = json.dumps(document, separators=(",", ":"), ensure_ascii=False)
        if "REPLACE_" in encoded:
            raise ValueError(f"Unresolved placeholder in {name}")
        if "Statement" in document and len(encoded) > 6144:
            raise ValueError(f"{name} exceeds 6144 IAM policy characters; do not broaden or truncate it.")
        manifest["files"][name] = {"characters": len(encoded), "sha256": hashlib.sha256(encoded.encode()).hexdigest()}
    for name, document in documents.items():
        (destination / name).write_text(json.dumps(document, separators=(",", ":")) + "\n", encoding="utf-8")
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"phase": args.phase, "files": len(documents), "aws_calls": False,
                      "boundary_characters": manifest["files"]["runtime-boundary.json"]["characters"]}))


if __name__ == "__main__":
    main()
