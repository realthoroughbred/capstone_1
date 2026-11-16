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


# Slack reporting. The Incoming Webhook URL is a bearer secret: it is read from
# Secrets Manager at send time and must never be logged, returned or stored.
SLACK_WEBHOOK_PREFIX = "https://hooks.slack.com/services/"
SLACK_TIMEOUT_SECONDS = 3
# status -> (emoji, attachment colour, headline)
SLACK_STYLE = {
    "REMEDIATED": ("\u2705", "#2eb886", "보안 그룹 위협 탐지 및 자동 복구 성공"),
    "DRY_RUN": ("\U0001F9EA", "#439fe0", "DRY_RUN: 복구 대상 탐지 (변경 없음)"),
    "REJECTED": ("\u26D4", "#daa038", "안전성 검증으로 복구 거부"),
    "FAILED": ("\u274C", "#a30200", "복구 작업 실패"),
}


def post_json(url, payload, timeout=SLACK_TIMEOUT_SECONDS):
    # Imported on first use: urllib.request loads ssl and http, which every cold
    # start (including Slack-disabled deployments and the Inspector Lambda) would
    # otherwise pay for before any remediation runs.
    import urllib.request

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            # A webhook never needs a redirect; refusing one keeps the POST on the validated host.
            return None

    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
        return response.status


def _slack_text(value):
    # Slack mrkdwn control characters; values are constants today, but never trust them.
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _slack_action(result):
    count = len(result.get("before_rule_ids") or [])
    status = result["status"]
    if status == "REMEDIATED":
        return f"월드 SSH(22) 인바운드 규칙 {count}개 제거 후 재검증 통과"
    if status == "DRY_RUN":
        return f"월드 SSH(22) 인바운드 규칙 {count}개 제거 예정. 변경하지 않음"
    if status == "REJECTED":
        # Re-checks run before each revoke and after the last one, so a refusal can
        # arrive after earlier rules were already removed. Never claim "unchanged".
        return "추가 변경 없이 중단. 중단 전에 일부 규칙이 이미 제거됐을 수 있으니 보안 그룹의 현재 규칙을 확인"
    return "복구 미완료. 보안 그룹 규칙을 수동으로 확인 필요"


def slack_message(result, project, target, duration_ms, when):
    """Build the Block Kit payload for one allowlisted result."""
    emoji, color, headline = SLACK_STYLE[result["status"]]
    group = target if isinstance(target, str) and re.fullmatch(r"sg-[a-f0-9]{8,17}", target) else "확인 불가"
    stamp = f"<!date^{int(when.timestamp())}^{{date_num}} {{time_secs}}|{when.isoformat(timespec='seconds')}>"
    fields = [
        ("프로젝트", _slack_text(project)),
        ("처리 결과", f"*{result['status']}*"),
        ("대상 Security Group", f"`{_slack_text(group)}`"),
        ("수행한 조치", _slack_action(result)),
        ("처리 시각", stamp),
        ("Lambda 실행 시간", f"{duration_ms} ms" if isinstance(duration_ms, int) else "측정 불가"),
    ]
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} Self-Healing {result['status']}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{headline}*"}},
        {"type": "section", "fields": [{"type": "mrkdwn", "text": f"*{name}*\n{value}"} for name, value in fields]},
    ]
    if result["status"] in ("REJECTED", "FAILED") and result.get("reason"):
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                                                   "text": f"*사유*\n`{_slack_text(result['reason'])}`"}})
    if result.get("evidence_saved") is False:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
                       "*S3 증적 저장 실패*\n보안 그룹 처리 결과는 위와 같습니다. Lambda가 재시도되며, 처리 기록은 CloudWatch 로그에서 확인하세요."}})
    return {"text": f"{emoji} [{_slack_text(project)}] Self-Healing {result['status']}: {group}",
            "attachments": [{"color": color, "blocks": blocks}]}


def _slack_webhook(get_secrets, secret_id):
    try:
        value = get_secrets().get_secret_value(SecretId=secret_id).get("SecretString") or ""
    except Exception:
        raise Rejected("slack_secret_unavailable") from None
    try:
        parsed = json.loads(value)
    except ValueError:
        parsed = None  # A plaintext secret holds the URL itself.
    if isinstance(parsed, dict):
        value = parsed.get("webhook_url") or ""
    url = value.strip() if isinstance(value, str) else ""
    require(bool(url), "slack_webhook_missing")
    require(url.startswith(SLACK_WEBHOOK_PREFIX) and len(url) > len(SLACK_WEBHOOK_PREFIX), "slack_webhook_invalid")
    return url


def notify_slack(result, env, get_secrets, target=None, duration_ms=None, post=post_json, now=None):
    """Best-effort report of a REMEDIATED/DRY_RUN/REJECTED/FAILED result.

    Never raises: a Slack, network or Secrets Manager problem must not change the
    remediation outcome. Only constant reason codes are logged, never provider
    errors, which can echo the webhook URL.
    """
    try:
        return _send_slack(result, env, get_secrets, target, duration_ms, post, now)
    except Exception:
        # Even bad inputs or a failing log write end here, never in the caller.
        return "FAILED"


def _send_slack(result, env, get_secrets, target, duration_ms, post, now):
    secret_id = env.get("SLACK_WEBHOOK_SECRET_ARN", "")
    if not secret_id or result.get("status") not in SLACK_STYLE:
        return "SKIPPED"
    reason = None
    try:
        url = _slack_webhook(get_secrets, secret_id)
        payload = slack_message(result, env.get("PROJECT", "unknown"), result.get("resource_id") or target,
                                duration_ms, now or datetime.now(timezone.utc))
        try:
            sent = post(url, payload) == 200
        except Exception:
            sent = False
        if not sent:
            reason = "slack_post_failed"
    except Rejected as exc:
        reason = str(exc)
    except Exception:
        reason = "slack_notification_error"
    outcome = {"slack_notification": "SENT" if reason is None else "FAILED", "status": result["status"]}
    if reason:
        outcome["reason"] = reason
    audit(outcome)
    return outcome["slack_notification"]
