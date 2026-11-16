"""Offline tests of the Slack report; fakes never contact Slack or AWS."""

import contextlib
import copy
import http.server
import io
import json
import os
import subprocess
import sys
import threading
import time
import types
import unittest
import unittest.mock
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from automation.common import SLACK_STYLE, notify_slack, post_json, slack_message
from automation.sg_healing import handle, lambda_handler
from tests.test_healing_sg import ENV as BASE_ENV, EVENT, SG, STS, EC2, rule

ROOT = Path(__file__).resolve().parents[1]

SECRET_ARN = "arn:aws:secretsmanager:ap-northeast-2:123456789012:secret:team4/notifications/slack-webhook-AbCdEf"
WEBHOOK = "https://hooks.slack.com/services/T00000000/B00000000/SECRETSECRETSECRET"
ENV = dict(BASE_ENV, SLACK_WEBHOOK_SECRET_ARN=SECRET_ARN)
NOW = datetime(2026, 10, 23, 13, 48, 5, tzinfo=timezone.utc)


class Secrets:
    def __init__(self, value=WEBHOOK, error=None):
        self.value, self.error, self.requests = value, error, []

    def get_secret_value(self, **kwargs):
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        return {"SecretString": self.value}


class Post:
    def __init__(self, status=200, error=None):
        self.status, self.error, self.calls = status, error, []

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        if self.error:
            raise self.error
        return self.status


def notify(result, post=None, secrets=None, env=None, **kwargs):
    post = post or Post()
    secrets = secrets or Secrets()
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        outcome = notify_slack(result, env or ENV, lambda: secrets, post=post, now=NOW, **kwargs)
    return outcome, post, secrets, log.getvalue()


def remediated(**changes):
    return dict({"status": "REMEDIATED", "resource_id": SG, "before_rule_ids": ["sgr-public-ssh"],
                 "handler_duration_ms": 1343}, **changes)


class SlackMessageTests(unittest.TestCase):
    def test_success_posts_required_fields_to_secret_url(self):
        outcome, post, secrets, log = notify(remediated(), duration_ms=1343)
        self.assertEqual("SENT", outcome)
        self.assertEqual([{"SecretId": SECRET_ARN}], secrets.requests)
        url, payload = post.calls[0]
        self.assertEqual(WEBHOOK, url)
        text = json.dumps(payload, ensure_ascii=False)
        for expected in ("team4", "REMEDIATED", SG, "월드 SSH(22) 인바운드 규칙 1개 제거", "1343 ms",
                         "2026-10-23T13:48:05+00:00", "<!date^"):
            self.assertIn(expected, text)
        self.assertNotIn("사유", text)
        self.assertNotIn("SECRETSECRET", text + log)

    def test_each_status_has_a_distinct_message(self):
        results = {
            "REMEDIATED": remediated(),
            "DRY_RUN": remediated(status="DRY_RUN", action="would_revoke_world_ssh"),
            "REJECTED": {"status": "REJECTED", "reason": "security_group_has_network_interfaces"},
            "FAILED": {"status": "FAILED", "reason": "security_group_revoke_failed"},
        }
        seen = set()
        for status, result in results.items():
            with self.subTest(status=status):
                payload = slack_message(result, "team4", SG, 20, NOW)
                attachment = payload["attachments"][0]
                text = json.dumps(payload, ensure_ascii=False)
                self.assertEqual(SLACK_STYLE[status][1], attachment["color"])
                self.assertIn(status, payload["text"])
                self.assertEqual("header", attachment["blocks"][0]["type"])
                self.assertIn(SG, text)
                self.assertEqual(status in ("REJECTED", "FAILED"), "사유" in text)
                if "reason" in result:
                    self.assertIn(result["reason"], text)
                seen.add((attachment["color"], payload["text"]))
        self.assertEqual(4, len(seen))

    def test_dry_run_states_that_nothing_changed(self):
        dry = json.dumps(slack_message(remediated(status="DRY_RUN"), "team4", SG, 5, NOW), ensure_ascii=False)
        self.assertIn("변경하지 않음", dry)

    def test_rejected_never_claims_the_group_is_unchanged(self):
        # A refusal can follow earlier revokes, so the message must send people to the live rules.
        text = json.dumps(slack_message({"status": "REJECTED", "reason": "x"}, "team4", SG, 5, NOW),
                          ensure_ascii=False)
        self.assertIn("이미 제거됐을 수 있", text)
        self.assertIn("현재 규칙을 확인", text)
        self.assertNotIn("변경하지 않음", text)

    def test_evidence_warning_only_when_the_evidence_write_failed(self):
        failed = json.dumps(slack_message(remediated(evidence_saved=False), "team4", SG, 5, NOW), ensure_ascii=False)
        normal = json.dumps(slack_message(remediated(), "team4", SG, 5, NOW), ensure_ascii=False)
        self.assertIn("S3 증적 저장 실패", failed)
        self.assertNotIn("S3 증적", normal)

    def test_untrusted_target_and_text_are_neutralised(self):
        payload = slack_message({"status": "REJECTED", "reason": "<!channel> & more"},
                                "team4", "<!channel> sg-fake", None, NOW)
        text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("<!channel>", text)
        self.assertIn("&lt;!channel&gt; &amp; more", text)
        self.assertIn("확인 불가", text)
        self.assertIn("측정 불가", text)

    def test_target_comes_from_event_when_result_has_none(self):
        _, post, _, _ = notify({"status": "REJECTED", "reason": "x"}, target=SG)
        self.assertIn(SG, json.dumps(post.calls[0][1]))

    def test_other_statuses_and_unconfigured_secret_send_nothing(self):
        for result in ({"status": "ALREADY_COMPLIANT"}, {"status": "IGNORED"}):
            outcome, post, secrets, _ = notify(result)
            self.assertEqual(("SKIPPED", [], []), (outcome, post.calls, secrets.requests))
        outcome, post, secrets, _ = notify(remediated(), env=BASE_ENV)
        self.assertEqual(("SKIPPED", [], []), (outcome, post.calls, secrets.requests))


class SlackFailureTests(unittest.TestCase):
    def assert_failed(self, reason, **kwargs):
        outcome, post, _, log = notify(remediated(), **kwargs)
        self.assertEqual("FAILED", outcome)
        self.assertIn(reason, log)
        self.assertNotIn("SECRETSECRET", log)
        self.assertNotIn("hooks.slack.com", log)
        return post

    def test_send_failure_is_reported_without_raising_or_leaking_url(self):
        post = Post(error=OSError("failed POST " + WEBHOOK))
        self.assert_failed("slack_post_failed", post=post)
        self.assertEqual(1, len(post.calls))

    def test_non_200_response_is_a_failure(self):
        self.assert_failed("slack_post_failed", post=Post(status=404))

    def test_missing_webhook_value(self):
        for value in ("", "   ", "{}", '{"webhook_url": ""}', None):
            with self.subTest(value=value):
                post = self.assert_failed("slack_webhook_missing", secrets=Secrets(value))
                self.assertEqual([], post.calls)

    def test_webhook_json_secret_is_supported(self):
        outcome, post, _, _ = notify(remediated(), secrets=Secrets(json.dumps({"webhook_url": WEBHOOK})))
        self.assertEqual(("SENT", WEBHOOK), (outcome, post.calls[0][0]))

    def test_non_slack_or_insecure_url_is_never_contacted(self):
        for value in ("https://evil.example/services/T/B/X", "http://hooks.slack.com/services/T/B/X",
                      "https://hooks.slack.com/", "https://hooks.slack.com.evil.example/services/T/B/X"):
            with self.subTest(value=value):
                post = self.assert_failed("slack_webhook_invalid", secrets=Secrets(value))
                self.assertEqual([], post.calls)

    def test_secret_lookup_failure(self):
        post = self.assert_failed("slack_secret_unavailable", secrets=Secrets(error=RuntimeError(WEBHOOK)))
        self.assertEqual([], post.calls)

    def test_unexpected_error_never_escapes(self):
        log = io.StringIO()
        def broken():
            raise ValueError("boom " + WEBHOOK)
        with contextlib.redirect_stdout(log):
            self.assertEqual("FAILED", notify_slack(remediated(), ENV, broken, post=Post()))
        self.assertNotIn("SECRETSECRET", log.getvalue())


class S3:
    def __init__(self, error=None):
        self.error, self.puts = error, []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        if self.error:
            raise self.error


class HandleRunner:
    """Runs sg_healing.handle with fakes; mixed into the test cases below."""

    def run_handle(self, ec2=None, env=None, event=None, post=None, secrets=None, s3=None):
        self.ec2, self.post = ec2 or EC2(), post or Post()
        secrets = secrets or Secrets()
        order = []
        original = self.post.__call__
        def recording_post(url, payload):
            order.append(("slack", len(self.ec2.calls)))
            return original(url, payload)
        log = io.StringIO()
        try:
            with contextlib.redirect_stdout(log):
                return handle(event or copy.deepcopy(EVENT), env or dict(ENV, DRY_RUN="false"),
                              lambda: (self.ec2, STS(), s3 or S3()), lambda: secrets, post=recording_post)
        finally:  # keep the log even when handle() raises
            self.order, self.log = order, log.getvalue()


class HandlerIntegrationTests(HandleRunner, unittest.TestCase):
    def test_remediated_report_is_sent_after_the_revoke(self):
        result = self.run_handle()
        self.assertEqual("REMEDIATED", result["status"])
        self.assertEqual([("slack", 1)], self.order)  # one revoke had already happened
        self.assertIn("REMEDIATED", self.post.calls[0][1]["text"])
        self.assertIn("ms", json.dumps(self.post.calls[0][1]))  # handler_duration_ms is forwarded

    def test_dry_run_is_reported_without_mutation(self):
        result = self.run_handle(env=dict(ENV, DRY_RUN="true"))
        self.assertEqual("DRY_RUN", result["status"])
        self.assertEqual([], self.ec2.calls)
        self.assertIn("DRY_RUN", self.post.calls[0][1]["text"])

    def test_rejection_reports_reason_and_event_target(self):
        ec2 = EC2()
        ec2.enis = [{"NetworkInterfaceId": "eni-production"}]
        result = self.run_handle(ec2)
        self.assertEqual({"status": "REJECTED", "reason": "security_group_has_network_interfaces"}, result)
        text = json.dumps(self.post.calls[0][1])
        self.assertIn("security_group_has_network_interfaces", text)
        self.assertIn(SG, text)
        self.assertEqual([], ec2.calls)

    def test_failure_reports_known_reason_and_still_raises_sanitized_error(self):
        ec2 = EC2()
        ec2.revoke_error = "UnauthorizedOperation"
        with self.assertRaisesRegex(RuntimeError, "^remediation_or_verification_failed$"):
            self.run_handle(ec2)
        text = json.dumps(self.post.calls[0][1])
        self.assertIn("FAILED", text)
        self.assertIn("security_group_revoke_failed", text)

    def test_unknown_failure_text_is_not_forwarded_to_slack(self):
        ec2 = EC2()
        ec2.describe_security_groups = lambda **kw: (_ for _ in ()).throw(RuntimeError("secret detail"))
        with self.assertRaises(RuntimeError):
            self.run_handle(ec2)
        text = json.dumps(self.post.calls[0][1])
        self.assertIn("remediation_or_verification_failed", text)
        self.assertNotIn("secret detail", text)

    def test_slack_outage_does_not_change_any_outcome(self):
        for label, kwargs in (("post", {"post": Post(error=OSError("down"))}),
                              ("secret", {"secrets": Secrets(error=RuntimeError("denied"))}),
                              ("missing", {"secrets": Secrets("")}),
                              ("both", {"post": Post(error=OSError("down")),
                                        "secrets": Secrets(error=RuntimeError("denied"))})):
            with self.subTest(label=label):
                result = self.run_handle(**kwargs)
                self.assertEqual("REMEDIATED", result["status"])
                self.assertEqual("PASS", result["verification"])
                self.assertEqual([r for r in self.ec2.rules if r["SecurityGroupRuleId"] == "sgr-public-ssh"], [])
                self.assertIn('"slack_notification":"FAILED"', self.log)

    def test_slack_outage_does_not_hide_rejection_or_failure(self):
        ec2 = EC2()
        ec2.group["Tags"] = []
        self.assertEqual("REJECTED", self.run_handle(ec2, post=Post(error=OSError("down")))["status"])
        ec2 = EC2()
        ec2.revoke_error = "UnauthorizedOperation"
        with self.assertRaisesRegex(RuntimeError, "^remediation_or_verification_failed$"):
            self.run_handle(ec2, post=Post(error=OSError("down")))

    def test_ignored_and_duplicate_events_do_not_notify(self):
        event = copy.deepcopy(EVENT)
        event["detail"]["newEvaluationResult"]["complianceType"] = "COMPLIANT"
        self.assertEqual("IGNORED", self.run_handle(event=event)["status"])
        clean = EC2([rule("sgr-private", CidrIpv4="10.40.0.0/16")])
        self.assertEqual("ALREADY_COMPLIANT", self.run_handle(clean)["status"])
        self.assertEqual([], self.post.calls)

    def test_scope_checks_still_apply_before_any_report_or_write(self):
        ec2 = EC2()
        result = self.run_handle(ec2, event=dict(EVENT, account="999999999999"))
        self.assertEqual({"status": "REJECTED", "reason": "event_scope_mismatch"}, result)
        self.assertEqual([], ec2.calls)
        self.assertIn("event_scope_mismatch", json.dumps(self.post.calls[0][1]))

    def test_malformed_event_is_rejected_and_reported_with_unknown_target(self):
        result = self.run_handle(event={"source": "aws.config"})
        self.assertEqual("REJECTED", result["status"])
        self.assertIn("확인 불가", json.dumps(self.post.calls[0][1], ensure_ascii=False))


class EvidenceFailureTests(HandleRunner, unittest.TestCase):
    """F2: a failed S3 evidence write must not relabel a finished remediation as FAILED."""

    def live_env(self):
        return dict(ENV, DRY_RUN="false", EVIDENCE_BUCKET="team4-evidence")

    def test_revoked_group_is_reported_as_remediated_when_evidence_write_fails(self):
        s3 = S3(error=OSError("s3 throttled"))
        with self.assertRaisesRegex(RuntimeError, "^remediation_or_verification_failed$"):
            self.run_handle(env=self.live_env(), s3=s3)
        self.assertEqual([], [r for r in self.ec2.rules if r["SecurityGroupRuleId"] == "sgr-public-ssh"])
        self.assertEqual(1, len(s3.puts))
        self.assertEqual(1, len(self.post.calls))
        payload = self.post.calls[0][1]
        text = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(SLACK_STYLE["REMEDIATED"][1], payload["attachments"][0]["color"])
        self.assertIn("REMEDIATED", payload["text"])
        self.assertNotIn("FAILED", payload["text"])
        self.assertNotIn("복구 작업 실패", text)
        self.assertIn("S3 증적 저장 실패", text)

    def test_the_real_result_and_the_evidence_failure_are_both_logged(self):
        with self.assertRaises(RuntimeError):
            self.run_handle(env=self.live_env(), s3=S3(error=OSError("down")))
        lines = [json.loads(line) for line in self.log.splitlines()]
        result = next(line for line in lines if line.get("status") == "REMEDIATED")
        self.assertIs(False, result["evidence_saved"])
        self.assertEqual(SG, result["resource_id"])
        self.assertIn({"status": "FAILED", "reason": "evidence_write_failed"}, lines)

    def test_dry_run_is_still_reported_as_dry_run(self):
        with self.assertRaises(RuntimeError):
            self.run_handle(env=dict(self.live_env(), DRY_RUN="true"), s3=S3(error=OSError("down")))
        self.assertEqual([], self.ec2.calls)
        self.assertIn("DRY_RUN", self.post.calls[0][1]["text"])

    def test_retry_after_the_evidence_failure_is_a_silent_no_op(self):
        ec2, env = EC2(), self.live_env()
        with self.assertRaises(RuntimeError):
            self.run_handle(ec2, env=env, s3=S3(error=OSError("down")))
        self.assertEqual("ALREADY_COMPLIANT", self.run_handle(ec2, env=env, s3=S3())["status"])
        self.assertEqual(1, len(ec2.calls))  # revoked once, on the first attempt
        self.assertEqual([], self.post.calls)  # and only the first attempt reported

    def test_slack_outage_during_an_evidence_failure_keeps_the_original_error(self):
        with self.assertRaisesRegex(RuntimeError, "^remediation_or_verification_failed$"):
            self.run_handle(env=self.live_env(), s3=S3(error=OSError("down")), post=Post(error=OSError("down")))

    def test_evidence_is_still_written_before_the_report_on_success(self):
        s3 = S3()
        self.assertEqual("REMEDIATED", self.run_handle(env=self.live_env(), s3=s3)["status"])
        self.assertEqual(1, len(s3.puts))
        self.assertNotIn("S3 증적", json.dumps(self.post.calls[0][1], ensure_ascii=False))

    def test_remediation_failure_is_still_reported_as_failed(self):
        ec2 = EC2()
        ec2.revoke_error = "UnauthorizedOperation"
        s3 = S3()
        with self.assertRaises(RuntimeError):
            self.run_handle(ec2, env=self.live_env(), s3=s3)
        self.assertEqual([], s3.puts)  # nothing finished, so no evidence
        self.assertIn("security_group_revoke_failed", json.dumps(self.post.calls[0][1]))


class PartialRejectionTests(HandleRunner, unittest.TestCase):
    """F3: a refusal after the first revoke leaves the group partly changed."""

    def test_rejection_after_one_revoke_warns_that_rules_may_already_be_gone(self):
        ec2 = EC2([rule(), rule("sgr-v6", CidrIpv4=None, CidrIpv6="::/0")])
        original = ec2.revoke_security_group_ingress
        def revoke_then_attach(**kwargs):
            result = original(**kwargs)
            ec2.enis = [{"NetworkInterfaceId": "eni-attached-meanwhile"}]
            return result
        ec2.revoke_security_group_ingress = revoke_then_attach
        result = self.run_handle(ec2)
        self.assertEqual({"status": "REJECTED", "reason": "security_group_has_network_interfaces"}, result)
        self.assertEqual(1, len(ec2.calls))  # the first rule is gone, the second was never touched
        self.assertEqual(["sgr-v6"], [r["SecurityGroupRuleId"] for r in ec2.rules])
        text = json.dumps(self.post.calls[0][1], ensure_ascii=False)
        self.assertIn("이미 제거됐을 수 있", text)
        self.assertNotIn("변경하지 않음", text)


class StubBoto:
    """Stand-in for boto3/botocore so the Lambda entry point runs without either installed."""

    def __init__(self, secret_value="not-a-slack-webhook"):
        self.clients, self.secret_value = [], secret_value

    def modules(self):
        outer = self

        class Config:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class Client:
            def __init__(self, name, region_name, config):
                self.name, self.region, self.config = name, region_name, config

            def get_secret_value(self, **kwargs):
                return {"SecretString": outer.secret_value}

        def client(name, region_name=None, config=None):
            made = Client(name, region_name, config)
            outer.clients.append(made)
            return made

        boto3 = types.ModuleType("boto3")
        boto3.client = client
        botocore = types.ModuleType("botocore")
        botocore_config = types.ModuleType("botocore.config")
        botocore_config.Config = Config
        botocore.config = botocore_config
        return {"boto3": boto3, "botocore": botocore, "botocore.config": botocore_config}


class LambdaEntryPointTests(unittest.TestCase):
    """F4: the Secrets Manager client must make exactly one attempt."""

    def invoke(self, env):
        stub = StubBoto()
        log = io.StringIO()
        with unittest.mock.patch.dict(os.environ, env, clear=True), \
                unittest.mock.patch.dict(sys.modules, stub.modules()), \
                contextlib.redirect_stdout(log):
            # A malformed event is rejected before any EC2 call, and the stub secret is not a
            # Slack URL, so nothing can reach the network.
            result = lambda_handler({"source": "aws.config"}, None)
        return result, stub, log.getvalue()

    def test_secrets_client_uses_a_single_attempt_and_short_timeouts(self):
        result, stub, _ = self.invoke(dict(ENV))
        self.assertEqual({"status": "REJECTED", "reason": "unexpected_event_type"}, result)
        secrets = [c for c in stub.clients if c.name == "secretsmanager"]
        self.assertEqual(1, len(secrets))
        self.assertEqual("ap-northeast-2", secrets[0].region)
        self.assertEqual({"connect_timeout": 2, "read_timeout": 3,
                          "retries": {"total_max_attempts": 1, "mode": "standard"}}, secrets[0].config.kwargs)

    def test_remediation_clients_keep_their_retry_budget(self):
        _, stub, _ = self.invoke(dict(ENV))
        for name in ("ec2", "sts", "s3"):
            with self.subTest(name=name):
                client = next(c for c in stub.clients if c.name == name)
                self.assertEqual({"connect_timeout": 3, "read_timeout": 5,
                                  "retries": {"max_attempts": 2, "mode": "standard"}}, client.config.kwargs)

    def test_no_secrets_client_without_a_configured_secret(self):
        result, stub, log = self.invoke(BASE_ENV)
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual([], [c for c in stub.clients if c.name == "secretsmanager"])
        self.assertNotIn("slack_notification", log)


class LazyImportTests(unittest.TestCase):
    """F6: the HTTP stack must not be loaded unless a message is actually posted."""

    def test_importing_the_handlers_does_not_load_urllib_request(self):
        code = ("import sys; import automation.common, automation.sg_healing;"
                "print('urllib.request' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual("False", out.stdout.strip(), out.stderr)

    def test_slack_off_run_does_not_load_urllib_request(self):
        code = ("import sys, contextlib, io\n"
                "from automation.sg_healing import handle\n"
                "with contextlib.redirect_stdout(io.StringIO()):\n"
                "    handle({'source': 'x'}, {}, lambda: (None, None, None), lambda: None)\n"
                "print('urllib.request' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual("False", out.stdout.strip(), out.stderr)


class _Server(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass  # A client that timed out and hung up is expected here.


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.received.append((self.path, self.headers.get("Content-Type"), json.loads(body)))
        if self.path == "/ok":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/ok")
            self.end_headers()
        elif self.path == "/slow":
            time.sleep(1.5)
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


class PostJsonTests(unittest.TestCase):
    """The real HTTP helper, against a throwaway 127.0.0.1 server (never Slack)."""

    @classmethod
    def setUpClass(cls):
        cls.server = _Server(("127.0.0.1", 0), _Handler)
        cls.server.received = []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_posts_json_and_returns_the_status(self):
        self.assertEqual(200, post_json(self.base + "/ok", {"text": "hi"}, timeout=2))
        self.assertEqual(("/ok", "application/json", {"text": "hi"}), self.server.received[-1])

    def test_redirects_are_refused_instead_of_followed(self):
        before = len(self.server.received)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            post_json(self.base + "/redirect", {}, timeout=2)
        self.assertEqual(302, caught.exception.code)
        self.assertEqual(before + 1, len(self.server.received))  # /ok was never requested

    def test_error_status_and_timeout_raise(self):
        with self.assertRaises(urllib.error.HTTPError):
            post_json(self.base + "/missing", {}, timeout=2)
        started = time.monotonic()
        with self.assertRaises(OSError):
            post_json(self.base + "/slow", {}, timeout=0.3)
        self.assertLess(time.monotonic() - started, 1.4)

    def test_notify_slack_turns_these_failures_into_a_logged_code(self):
        for path in ("/redirect", "/missing"):
            with self.subTest(path=path):
                log = io.StringIO()
                secrets = Secrets(WEBHOOK)
                with contextlib.redirect_stdout(log), unittest.mock.patch(
                        "automation.common.SLACK_WEBHOOK_PREFIX", self.base + path):
                    secrets.value = self.base + path + "/token"
                    outcome = notify_slack(remediated(), ENV, lambda: secrets, now=NOW)
                self.assertEqual("FAILED", outcome)
                self.assertIn("slack_post_failed", log.getvalue())
                self.assertNotIn(self.base, log.getvalue())


class SlackIsolationTests(HandleRunner, unittest.TestCase):
    """F10: nothing the Slack code does may replace a result or an exception of the handler."""

    def test_notify_slack_swallows_bad_input_and_logging_errors(self):
        broken_env = unittest.mock.MagicMock()
        broken_env.get.side_effect = RuntimeError("env exploded " + WEBHOOK)
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            self.assertEqual("FAILED", notify_slack(remediated(), broken_env, lambda: Secrets()))
            self.assertEqual("FAILED", notify_slack(None, ENV, lambda: Secrets()))
            self.assertEqual("FAILED", notify_slack({"status": "FAILED"}, ENV, lambda: Secrets(), post=Post(),
                                                    now="not a datetime"))
        self.assertNotIn("SECRETSECRET", log.getvalue())
        with unittest.mock.patch("automation.common.audit", side_effect=OSError("stdout closed")):
            self.assertEqual("FAILED", notify_slack(remediated(), ENV, lambda: Secrets(), post=Post(), now=NOW))

    def test_a_raising_notifier_does_not_change_the_returned_result(self):
        with unittest.mock.patch("automation.sg_healing.notify_slack", side_effect=RuntimeError("slack exploded")):
            result = self.run_handle()
            self.assertEqual("REMEDIATED", result["status"])
            self.assertEqual("PASS", result["verification"])
            rejected = self.run_handle(event={"source": "aws.config"})
            self.assertEqual({"status": "REJECTED", "reason": "unexpected_event_type"}, rejected)

    def test_a_raising_notifier_does_not_replace_the_sanitized_failure(self):
        ec2 = EC2()
        ec2.revoke_error = "UnauthorizedOperation"
        with unittest.mock.patch("automation.sg_healing.notify_slack", side_effect=ValueError("slack exploded")):
            with self.assertRaises(RuntimeError) as caught:
                self.run_handle(ec2)
        self.assertEqual("remediation_or_verification_failed", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)  # raised "from None": no Slack detail attached

    def test_a_raising_notifier_does_not_replace_the_evidence_failure_error(self):
        with unittest.mock.patch("automation.sg_healing.notify_slack", side_effect=ValueError("slack exploded")):
            with self.assertRaisesRegex(RuntimeError, "^remediation_or_verification_failed$"):
                self.run_handle(env=dict(ENV, DRY_RUN="false", EVIDENCE_BUCKET="b"), s3=S3(error=OSError("down")))

    def test_a_broken_clock_in_the_report_path_is_contained(self):
        # Duration fallback reads the clock; a failure there must not escape either.
        calls = iter([0.0])
        def clock():
            try:
                return next(calls)
            except StopIteration:
                raise OSError("clock failure") from None
        with contextlib.redirect_stdout(io.StringIO()):
            result = handle({"source": "aws.config"}, dict(ENV), lambda: (EC2(), STS(), S3()),
                            lambda: Secrets(), post=Post(), clock=clock)
        self.assertEqual("REJECTED", result["status"])


if __name__ == "__main__":
    unittest.main()
