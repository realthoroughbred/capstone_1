#!/usr/bin/env python3
"""Confirm expected runtime digests for the three existing demo Deployments."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from automation.runtime_verify import verify_live_deployments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--namespace", default="demo")
    parser.add_argument("--image", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--evidence", default="evidence/deployment-runtime.json")
    args = parser.parse_args()
    result = verify_live_deployments(args.context, args.namespace, args.image,
        ["server", "client", "unauthorized"], dict(os.environ), timeout=args.timeout_seconds)
    destination = Path(args.evidence)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
