from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.operator_approval import sign_approval


TOKEN = "site-dpi-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
SITE_ID = "private-site-id"
OPERATOR_ID = "op_" + "5" * 24
INITIAL = {"dpi": False, "loggingTraffic": False}


class SiteDpiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.temp.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as handle:
            handle.write(TOKEN)
        self.operator_key = b"o" * 32
        self.operator_key_file = os.path.join(self.temp.name, "operator-key")
        fd = os.open(self.operator_key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(self.operator_key)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._ref_key = b"r" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-reference-key")
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.client._site_ids_by_ref[OTHER_SITE_REF] = "other-private-site-id"
        self.state = dict(INITIAL)
        self.transport_calls: list[tuple[str, str, bytes | None]] = []
        self.put_calls: list[tuple[str, dict[str, bool]]] = []
        self.put_mode = "normal"

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(token, "synthetic-upstream-token")
            self.assertEqual(path, f"/openapi/v1/ctrl/sites/{SITE_ID}/applicationControl/status")
            if method == "GET":
                self.assertIsNone(body)
                return {"result": dict(self.state)}
            self.assertEqual(method, "PUT")
            self.assertIsInstance(body, bytes)
            decoded = json.loads(body)
            self.assertEqual(set(decoded), {"dpi", "loggingTraffic"})
            self.assertIs(type(decoded["dpi"]), bool)
            self.assertIs(type(decoded["loggingTraffic"]), bool)
            self.put_calls.append((path, decoded))
            if self.put_mode == "timeout":
                raise OSError("private controller diagnostic")
            self.state = dict(decoded)
            if self.put_mode == "mismatch":
                self.state["loggingTraffic"] = not self.state["loggingTraffic"]
            return {"result": None}

        self.transport_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.transport_patch.start()
        self.access_patch = patch.object(
            self.client, "_access_token", return_value="synthetic-upstream-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": self.token_file,
            "OMADA_ENABLE_WRITES": "false",
            "OMADA_CHANGE_JOURNAL_DIR": self.journal_dir,
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": self.operator_key_file,
        })
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.runtime_patch = patch.object(main, "_JOURNAL_RUNTIME", None)
        self.runtime_patch.start()
        self.plans_patch = patch.object(main, "_SITE_DPI_PLANS", None)
        self.plans_patch.start()
        self.active_patch = patch.object(main, "_ACTIVE_APPROVAL", None)
        self.active_patch.start()
        self.consumed_patch = patch.dict(main._CONSUMED_APPROVALS, {}, clear=True)
        self.consumed_patch.start()
        self.logs = io.StringIO()
        self.print_patch = patch.object(
            builtins, "print", lambda *args, **_kwargs: self.logs.write(
                " ".join(map(str, args)) + "\n"))
        self.print_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        runtime = main._JOURNAL_RUNTIME
        if runtime is not None:
            runtime.close()
        self.print_patch.stop()
        self.plans_patch.stop()
        self.runtime_patch.stop()
        self.active_patch.stop()
        self.consumed_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.transport_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def _upstream_path() -> str:
        return f"/openapi/v1/ctrl/sites/{SITE_ID}/applicationControl/status"

    @staticmethod
    def _read_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/application-control"

    @staticmethod
    def _preview_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/application-control-preview"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers: dict[str, str] = {}
        encoded = None
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":"))
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        status = response.status
        connection.close()
        return status, parsed

    def preview(self, changes: dict[str, object] | None = None) -> dict[str, object]:
        status, result = self.request(
            "POST", self._preview_path(), token=TOKEN,
            body={"changes": changes or {"dpi": True}, "disruption_confirmed": True})
        self.assertEqual(status, 200, result)
        return result

    def approval(self, preview: dict[str, object], *, key: bytes | None = None,
                  nonce: str | None = None):
        request = preview["approval_request"]
        assert isinstance(request, dict)
        now = int(time.time())
        with patch("app.operator_approval.secrets.token_hex", return_value=nonce) if nonce else _nullcontext():
            return sign_approval(
                key or self.operator_key, operation="site-dpi", plan_id=preview["plan_id"],
                plan_digest=request["digest"], operator_id=OPERATOR_ID,
                expires_at=now + 120, now=now)

    def apply(self, preview: dict[str, object], approval: dict[str, object]):
        return self.request("POST", f"/v1/site-dpi-plans/{preview['plan_id']}/apply",
                            token=TOKEN, body={"approval": approval})

    def test_auth_get_preview_exact_warnings_and_complete_binding(self) -> None:
        status, unauth = self.request("GET", self._read_path())
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])
        status, result = self.request("GET", self._read_path(), token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], INITIAL)
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])
        status, unknown = self.request("GET", self._read_path("c" * 24), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(unknown["error"], "site_ref_unknown")

        preview = self.preview({"loggingTraffic": True})
        self.assertEqual(preview["before"], INITIAL)
        self.assertEqual(preview["target"], {"dpi": False, "loggingTraffic": True})
        self.assertEqual(preview["rollback"], INITIAL)
        self.assertEqual(preview["warnings"], [
            "DPI side effects are unknown and may depend on controller behavior.",
            "Traffic logging can record usage data.",
        ])
        request = preview["approval_request"]
        self.assertEqual(request["before"], INITIAL)
        self.assertEqual(request["target"], preview["target"])
        self.assertEqual(request["target_refs"], {"site_ref": SITE_REF})

        # Approval digest changes when either boolean in the bound state changes.
        plan = main._SITE_DPI_PLANS.plans[preview["plan_id"]]
        original_before, original_target = dict(plan["before"]), dict(plan["target"])
        # Keep the one-field-change shape valid while changing the unchanged
        # DPI value in both complete states after the preview was signed.
        plan["before"]["dpi"] = True
        plan["target"]["dpi"] = True
        approval = self.approval(preview)
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, rejected = self.apply(preview, approval)
        self.assertEqual(status, 409)
        self.assertEqual(rejected["error"], "operator_approval_mismatch")
        self.assertEqual(self.put_calls, [])
        plan["before"], plan["target"] = original_before, original_target

    def test_missing_wrong_and_duplicate_approval_never_reach_wrong_write(self) -> None:
        preview = self.preview()
        apply_path = f"/v1/site-dpi-plans/{preview['plan_id']}/apply"
        status, off = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(off["error"], "writes_disabled")
        os.environ["OMADA_ENABLE_WRITES"] = "true"

        status, missing = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(missing["error"], "operator_approval_required")
        status, wrong = self.apply(preview, self.approval(preview, key=b"x" * 32))
        self.assertEqual(status, 409)
        self.assertIn(wrong["error"], {"operator_approval_invalid", "operator_approval_mismatch"})
        self.assertEqual(self.put_calls, [])

        first = self.approval(preview, nonce="1" * 32)
        status, applied = self.apply(preview, first)
        self.assertEqual(status, 200, applied)
        self.assertEqual(len(self.put_calls), 1)

        # A different valid plan carrying the already-consumed nonce is refused.
        second_preview = self.preview({"loggingTraffic": True})
        replayed_nonce = self.approval(second_preview, nonce="1" * 32)
        status, duplicate = self.apply(second_preview, replayed_nonce)
        self.assertEqual(status, 409)
        self.assertEqual(duplicate["error"], "operator_approval_reused")
        self.assertEqual(len(self.put_calls), 1)

    def test_stale_complete_state_and_exact_single_put_with_readback(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        preview = self.preview({"dpi": True})
        self.state["loggingTraffic"] = True
        status, stale = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 409)
        self.assertEqual(stale["error"], "state_changed")
        self.assertEqual(self.put_calls, [])

        self.state = dict(INITIAL)
        preview = self.preview({"loggingTraffic": True})
        status, applied = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 200, applied)
        target = {"dpi": False, "loggingTraffic": True}
        self.assertEqual(self.put_calls, [(self._upstream_path(), target)])
        self.assertEqual(self.state, target)
        self.assertEqual(applied["before"], INITIAL)
        self.assertEqual(applied["after"], target)
        self.assertEqual([call[0] for call in self.transport_calls[-3:]], ["GET", "PUT", "GET"])
        self.assertEqual(json.loads(self.transport_calls[-2][2]), target)
        self.assertEqual(len(self.put_calls), 1)

    def test_readback_mismatch_recovers_redacted_in_doubt_without_replay(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        self.put_mode = "mismatch"
        preview = self.preview({"dpi": True})
        status, failed = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 409)
        self.assertEqual(failed["error"], "change_in_doubt")
        self.assertEqual(len(self.put_calls), 1)

        runtime = main._JOURNAL_RUNTIME
        assert runtime is not None
        runtime.close()
        main._JOURNAL_RUNTIME = None
        main._SITE_DPI_PLANS = None
        status, doubts = self.request("GET", "/v1/change-plans/site-dpi/in-doubt", token=TOKEN)
        self.assertEqual(status, 200, doubts)
        self.assertEqual([row["plan_id"] for row in doubts["items"]], [preview["plan_id"]])
        status, inspected = self.request(
            "GET", f"/v1/change-plans/site-dpi/{preview['plan_id']}", token=TOKEN)
        self.assertEqual(status, 200, inspected)
        self.assertEqual(inspected["state"], "in_doubt")
        self.assertEqual(inspected["observation_note"],
                         "current_state_does_not_prove_original_write_outcome")
        status, replay = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len(self.put_calls), 1)

    def test_request_and_log_outputs_do_not_disclose_private_controller_data(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        preview = self.preview({"loggingTraffic": True})
        status, applied = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 200)
        combined = self.logs.getvalue() + json.dumps(applied)
        for private in (SITE_ID, "controller.example", "synthetic-upstream-token"):
            self.assertNotIn(private, combined)


class _FakeResponse:
    status = 200

    @staticmethod
    def read(_limit: int) -> bytes:
        return b'{"errorCode":0,"result":null}'

    @staticmethod
    def getheader(_name: str, default: str = "") -> str:
        return "application/json" if not default else default


class _FakeConnection:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple[str, str, bytes | None]] = []

    def request(self, method: str, path: str, *, body=None, headers=None) -> None:
        self.events.append("request")
        self.calls.append((method, path, body))

    @staticmethod
    def getresponse():
        return _FakeResponse()

    @staticmethod
    def close() -> None:
        pass


class SiteDpiTransportAllowlistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.path = f"/openapi/v1/ctrl/sites/{SITE_ID}/applicationControl/status"
        self.body = b'{"dpi":true,"loggingTraffic":false}'
        self.events: list[str] = []
        self.connection = _FakeConnection(self.events)

        def get_connection():
            self.events.append("connect")
            return self.connection

        self.connection_patch = patch.object(self.client, "_connection", side_effect=get_connection)
        self.connection_patch.start()

    def tearDown(self) -> None:
        self.connection_patch.stop()

    def test_only_fixed_put_path_method_and_full_two_bool_body_are_allowed(self) -> None:
        self.client._write_dispatch_guard = lambda: None
        invalid = (
            ("PATCH", self.path, self.body),
            ("PUT", self.path.replace("/ctrl/", "/other/"), self.body),
            ("PUT", self.path, b'{"dpi":true,"loggingTraffic":false,"other":1}'),
            ("PUT", self.path, b'{"dpi":true,"dpi":false,"loggingTraffic":false}'),
            ("PUT", self.path, b'{"dpi":1,"loggingTraffic":false}'),
        )
        for method, path, body in invalid:
            with self.subTest(method=method, path=path, body=body), self.assertRaises(OpenApiError) as raised:
                self.client._request_json(method, path, body=body, token="fake-token")
            self.assertEqual(raised.exception.code, "openapi_path_rejected")
        self.assertEqual(self.events, [])
        self.assertEqual(self.connection.calls, [])

    def test_dispatch_guard_runs_after_connect_immediately_before_fake_request(self) -> None:
        def guard():
            self.events.append("guard")

        self.client._write_dispatch_guard = guard
        self.client._request_json("PUT", self.path, body=self.body, token="fake-token")
        self.assertEqual(self.events, ["connect", "guard", "request"])
        self.assertEqual(self.connection.calls, [("PUT", self.path, self.body)])

        self.events.clear()
        self.connection.calls.clear()
        self.client._write_dispatch_guard = lambda: (_ for _ in ()).throw(
            RuntimeError("expired approval"))
        with self.assertRaises(RuntimeError):
            self.client._request_json("PUT", self.path, body=self.body, token="fake-token")
        self.assertEqual(self.events, ["connect"])
        self.assertEqual(self.connection.calls, [])


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, *_args):
        return False


def _nullcontext():
    return _NullContext()


if __name__ == "__main__":
    unittest.main()
