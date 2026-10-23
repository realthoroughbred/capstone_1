"""Small fail-closed helpers shared by Lambda handlers and local tests."""

import json
import re
import uuid
from datetime import datetime, timezone


class Rejected(ValueError):
    """An expected validation refusal, with a constant, non-sensitive reason."""


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def required(env, name):
    value = env.get(name, "")
    require(isinstance(value, str) and bool(value.strip()), "missing_configuration_" + name)
    return value.strip()


def dry_run(env):
    value = env.get("DRY_RUN", "true").lower()
    require(value in ("true", "false"), "invalid_dry_run")
    return value != "false"


def identity(env):
    account = required(env, "EXPECTED_ACCOUNT_ID")
    region = required(env, "EXPECTED_REGION")
    require(re.fullmatch(r"[0-9]{12}", account), "invalid_account_configuration")
    require(re.fullmatch(r"[a-z]{2}-[a-z]+-[0-9]", region), "invalid_region_configuration")
    return account, region


def aws_error_code(exc):
    # Never serialize provider errors; they may contain request data.
    return getattr(exc, "response", {}).get("Error", {}).get("Code", "Unknown")


def digest(value):
    require(isinstance(value, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", value), "invalid_image_digest")
    return value


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.tzinfo is not None, "timestamp_requires_timezone")
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        raise Rejected("invalid_timestamp") from None


def audit(result):
    # Callers pass only explicit, allowlisted operational fields, never the event.
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return result


def evidence(result, env, s3, prefix):
    """Persist only the allowlisted result; never the input event or AWS response."""
    record = dict(result, recorded_at=datetime.now(timezone.utc).isoformat())
    if env.get("EVIDENCE_BUCKET"):
        key = prefix + "/" + datetime.now(timezone.utc).strftime("%Y/%m/%d/") + uuid.uuid4().hex + ".json"
        s3.put_object(Bucket=env["EVIDENCE_BUCKET"], Key=key,
                      Body=(json.dumps(record, sort_keys=True) + "\n").encode(), ContentType="application/json")
        record["evidence_key"] = key
    return audit(record)
