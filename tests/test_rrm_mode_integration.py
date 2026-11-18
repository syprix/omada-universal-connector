from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.operator_approval import sign_approval


TOKEN = "rrm-mode-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
SITE_ID = "site_123"
OPERATOR_ID = "op_" + "5" * 24


class RrmModeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.temp.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as handle:
            handle.write(TOKEN)
        self.operator_key = b"k" * 32
        self.operator_key_file = os.path.join(self.temp.name, "operator-key")
        fd = os.open(self.operator_key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(self.operator_key)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._ref_key = b"r" * 32
        self.client.config = self.client.config.__class__(
            **{**self.client.config.__dict__, "reference_key_file": "synthetic-reference-key"})
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.state: dict[str, object] = {
            "mode": 0, "timeRangeEnable": False, "resource": 1,
            "timeRangeId": "", "timeRangeAction": 1,
        }
        self.bad_get: object | None = None
        self.put_failure = False
        self.put_then_timeout = False
        self.transport_calls: list[tuple[str, str, bytes | None]] = []

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(path, self._upstream_path())
            self.assertEqual(token, "synthetic-upstream-token")
            if method == "GET":
                self.assertIsNone(body)
                result = dict(self.state) if self.bad_get is None else self.bad_get
                return {"result": result}

            self.assertEqual(method, "PUT")
            self.assertIsInstance(body, bytes)
            decoded = json.loads(body)
            self.assertTrue(OmadaOpenApiClient._valid_rrm_mode_state(decoded))
            self.assertEqual(set(decoded), {
                "mode", "timeRangeEnable", "resource", "timeRangeId", "timeRangeAction",
            })
            if self.put_then_timeout:
                self.state = decoded
                raise OpenApiError("controller_unreachable")
            if self.put_failure:
                raise OpenApiError("controller_unreachable")
            self.state = decoded
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
        self.plans_patch = patch.object(main, "_RRM_MODE_PLANS", None)
        self.plans_patch.start()
        self.active_patch = patch.object(main, "_ACTIVE_APPROVAL", None)
        self.active_patch.start()
        self.consumed_patch = patch.dict(main._CONSUMED_APPROVALS, {}, clear=True)
        self.consumed_patch.start()
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
    def _upstream_path(controller_id: str = "ctrl") -> str:
        return f"/openapi/v1/{controller_id}/sites/{SITE_ID}/rrm/config"

    @staticmethod
    def _settings_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/wifi/optimization"

    @staticmethod
    def _preview_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/wifi/optimization-preview"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: dict[str, object] | None = None,
                raw_body: str | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers: dict[str, str] = {}
        encoded = raw_body
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is not None or raw_body is not None:
            if encoded is None:
                encoded = json.dumps(body, separators=(",", ":"))
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {}
        connection.close()
        return response.status, result

    def approval_body(self, preview: dict[str, object]) -> dict[str, object]:
        now = int(time.time())
        request = preview["approval_request"]
        assert isinstance(request, dict)
        approval = sign_approval(
            self.operator_key, operation="rrm-mode", plan_id=preview["plan_id"],
            plan_digest=request["digest"], operator_id=OPERATOR_ID,
            expires_at=now + 120, now=now)
        return {"approval": approval}

    def valid_preview(self, mode: int = 1) -> dict[str, object]:
        status, result = self.request(
            "POST", self._preview_path(), token=TOKEN,
            body={"changes": {"mode": mode}, "disruption_confirmed": True})
        self.assertEqual(status, 200, result)
        return result

    def test_auth_fixed_get_and_unknown_site(self) -> None:
        status, result = self.request("GET", self._settings_path())
        self.assertEqual(status, 401)
        self.assertEqual(result["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, result = self.request("GET", self._settings_path(), token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], {
            "mode": 0, "timeRangeEnable": False, "resource": 1,
            "timeRangeAction": 1,
        })
        self.assertTrue(result["partial"])
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])

        before = len(self.transport_calls)
        status, unknown = self.request("GET", self._settings_path("b" * 24), token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(len(self.transport_calls), before)
        self.assertNotIn(SITE_ID, json.dumps(unknown))

    def test_preview_blocks_incomplete_active_profile_and_unknown_states(self) -> None:
        invalid_states: tuple[object, ...] = (
            {"mode": 0, "timeRangeEnable": False, "resource": 1,
             "timeRangeId": ""},
            {"mode": 0, "timeRangeEnable": True, "resource": 1,
             "timeRangeId": "", "timeRangeAction": 1},
            {"mode": 0, "timeRangeEnable": False, "resource": 1,
             "timeRangeId": "profile-id", "timeRangeAction": 1},
            {"mode": 0, "timeRangeEnable": False, "resource": 1,
             "timeRangeId": "", "timeRangeAction": 1, "extension": 3},
            {"mode": 0, "timeRangeEnable": False, "resource": None,
             "timeRangeId": "", "timeRangeAction": 1},
            {"mode": 0, "timeRangeEnable": False, "resource": 3,
             "timeRangeId": "", "timeRangeAction": 1},
        )
        for state in invalid_states:
            with self.subTest(state=state):
                self.bad_get = state
                before_calls = len(self.transport_calls)
                status, result = self.request(
                    "POST", self._preview_path(), token=TOKEN,
                    body={"changes": {"mode": 1}, "disruption_confirmed": True})
                self.assertEqual(status, 400)
                self.assertEqual(result.get("error"), "rrm_state_unsupported")
                self.assertNotIn("plan_id", result)
                self.assertEqual(len([c for c in self.transport_calls if c[0] == "PUT"]), 0)
                self.assertGreater(len(self.transport_calls), before_calls)
        self.bad_get = None

        for body in (
            {"changes": {"mode": 1}},
            {"changes": {"mode": 1}, "disruption_confirmed": False},
            {"changes": {"mode": True}, "disruption_confirmed": True},
            {"changes": {"mode": 2}, "disruption_confirmed": True},
            {"changes": {"mode": 1, "extra": 0}, "disruption_confirmed": True},
            {"changes": {"mode": 1}, "disruption_confirmed": True, "extra": 0},
        ):
            status, result = self.request("POST", self._preview_path(), token=TOKEN, body=body)
            self.assertEqual(status, 400, body)
            self.assertEqual(result.get("status"), "error")

    def test_preview_approval_put_preserves_all_side_fields_readback_and_no_replay(self) -> None:
        status, no_auth = self.request(
            "POST", self._preview_path(),
            body={"changes": {"mode": 1}, "disruption_confirmed": True})
        self.assertEqual(status, 401)
        self.assertEqual(no_auth["error"], "unauthorized")

        preview = self.valid_preview()
        self.assertEqual(preview["before"], self.state)
        self.assertEqual(preview["target"], {
            "mode": 1, "timeRangeEnable": False, "resource": 1,
            "timeRangeId": "", "timeRangeAction": 1,
        })
        apply_path = f"/v1/rrm-mode-plans/{preview['plan_id']}/apply"
        status, no_auth = self.request("POST", apply_path, body={})
        self.assertEqual(status, 401)
        self.assertEqual(no_auth["error"], "unauthorized")

        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, missing = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(missing["error"], "operator_approval_required")
        self.assertFalse(any(method == "PUT" for method, _path, _body in self.transport_calls))

        status, applied = self.request("POST", apply_path, token=TOKEN,
                                       body=self.approval_body(preview))
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["after"], preview["target"])
        methods = [method for method, _path, _body in self.transport_calls]
        self.assertEqual(methods, ["GET", "GET", "GET", "PUT", "GET"])
        put_call = next(call for call in self.transport_calls if call[0] == "PUT")
        self.assertEqual(put_call[1], self._upstream_path())
        self.assertEqual(json.loads(put_call[2]), preview["target"])

        status, replay = self.request("POST", apply_path, token=TOKEN,
                                      body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len([c for c in self.transport_calls if c[0] == "PUT"]), 1)

    def test_stale_timeout_and_journal_recovery_never_replay(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        stale_preview = self.valid_preview()
        self.state["resource"] = 2
        stale_path = f"/v1/rrm-mode-plans/{stale_preview['plan_id']}/apply"
        status, stale = self.request("POST", stale_path, token=TOKEN,
                                     body=self.approval_body(stale_preview))
        self.assertEqual(status, 409)
        self.assertEqual(stale["error"], "state_changed")
        self.assertFalse(any(c[0] == "PUT" for c in self.transport_calls))

        self.state["resource"] = 1
        failed_preview = self.valid_preview()
        failed_path = f"/v1/rrm-mode-plans/{failed_preview['plan_id']}/apply"
        self.put_then_timeout = True
        status, failed = self.request("POST", failed_path, token=TOKEN,
                                      body=self.approval_body(failed_preview))
        self.assertEqual(status, 409)
        self.assertEqual(failed["error"], "change_in_doubt")
        self.assertEqual(len([c for c in self.transport_calls if c[0] == "PUT"]), 1)

        status, replay = self.request("POST", failed_path, token=TOKEN,
                                      body=self.approval_body(failed_preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        runtime = main._JOURNAL_RUNTIME
        self.assertIsNotNone(runtime)
        runtime.close()
        main._JOURNAL_RUNTIME = None
        main._RRM_MODE_PLANS = None
        status, items = self.request("GET", "/v1/change-plans/rrm-mode/in-doubt", token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(len(items["items"]), 1)
        self.assertEqual(items["items"][0]["plan_id"], failed_preview["plan_id"])

        status, replay_after_recovery = self.request(
            "POST", failed_path, token=TOKEN, body=self.approval_body(failed_preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay_after_recovery["error"], "plan_unavailable")
        self.assertEqual(len([c for c in self.transport_calls if c[0] == "PUT"]), 1)

    def test_controller_allowlist_is_exact_and_never_connects_in_this_test(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        path = self._upstream_path()
        valid_body = json.dumps(self.state, separators=(",", ":")).encode("ascii")
        connection_error = OpenApiError("connection_reached")
        with patch.object(client, "_connection", side_effect=connection_error):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", path, token="token")
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                client._request_json("PUT", path, body=valid_body, token="token")
            client._write_dispatch_guard = lambda: None
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("PUT", path, body=valid_body, token="token")
            forbidden = (
                ("GET", path + "?x=1", None),
                ("GET", self._upstream_path("other-controller"), None),
                ("POST", path, valid_body),
                ("PUT", path, b'{"mode":1}'),
                ("PUT", path, b'{"mode":1,"mode":0}'),
                ("PUT", path, json.dumps({**self.state, "extension": 1}).encode()),
                ("PUT", path, json.dumps({**self.state, "timeRangeId": "not-empty"}).encode()),
                ("PUT", path, json.dumps({**self.state, "timeRangeEnable": True}).encode()),
                ("PATCH", path, valid_body),
            )
            for method, rejected_path, body in forbidden:
                with self.subTest(method=method, path=rejected_path, body=body), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, rejected_path, body=body, token="token")


if __name__ == "__main__":
    unittest.main()
