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


SITE_REF = "a" * 24
SITE_ID = "site_1"
OPERATOR_ID = "op_" + "5" * 24


class BandSteeringIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.tempdir.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.token = "fixture-caller-token-0123456789abcdef"
        self.token_file = os.path.join(self.tempdir.name, "caller-token")
        with open(self.token_file, "w", encoding="utf-8") as handle:
            handle.write(self.token)
        self.operator_key = b"o" * 32
        self.operator_key_file = os.path.join(self.tempdir.name, "operator-approval-key")
        fd = os.open(self.operator_key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(self.operator_key)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id-file", "secret-file",
            cert_sha256="a" * 64))
        # A persistent, independent reference key is required to open the real
        # temporary journal; all controller access below is stubbed locally.
        self.client._ref_key = b"r" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-reference-key")
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.mode = 0
        self.extra_get_field = False
        self.fail_patch = False
        self.apply_then_fail = False
        self.transport_calls: list[tuple[str, str, bytes | None]] = []

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(token, "fixture-upstream-token")
            self.assertEqual(path, self._upstream_path())
            if method == "GET":
                self.assertIsNone(body)
                result = {"bandSteeringForMultiBand": {"mode": self.mode}}
                if self.extra_get_field:
                    result["unexpected"] = "must fail closed"
                return {"result": result}

            self.assertEqual(method, "PATCH")
            self.assertIsInstance(body, bytes)
            decoded = json.loads(body)
            self.assertEqual(decoded, {"bandSteeringForMultiBand": {"mode": decoded.get("bandSteeringForMultiBand", {}).get("mode")}})
            mode = decoded["bandSteeringForMultiBand"]["mode"]
            self.assertIs(type(mode), int)
            self.assertIn(mode, (0, 1, 2))
            if self.apply_then_fail:
                self.mode = mode
                raise OpenApiError("controller_unreachable")
            if self.fail_patch:
                raise OpenApiError("controller_unreachable")
            self.mode = mode
            return {"result": None}

        self.transport_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.transport_patch.start()
        self.access_patch = patch.object(self.client, "_access_token", return_value="fixture-upstream-token")
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
        self.plans_patch = patch.object(main, "_BAND_STEERING_PLANS", None)
        self.plans_patch.start()
        self.active_approval_patch = patch.object(main, "_ACTIVE_APPROVAL", None)
        self.active_approval_patch.start()
        self.consumed_approvals_patch = patch.dict(main._CONSUMED_APPROVALS, {}, clear=True)
        self.consumed_approvals_patch.start()
        self.logs = io.StringIO()
        self.log_patch = patch.object(
            builtins, "print",
            lambda *args, **_kwargs: self.logs.write(" ".join(map(str, args)) + "\n"))
        self.log_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.log_patch.stop()
        runtime = main._JOURNAL_RUNTIME
        if runtime is not None:
            runtime.close()
        self.plans_patch.stop()
        self.runtime_patch.stop()
        self.active_approval_patch.stop()
        self.consumed_approvals_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.transport_patch.stop()
        self.tempdir.cleanup()

    @staticmethod
    def _upstream_path(controller_id: str = "ctrl") -> str:
        return f"/openapi/v1/{controller_id}/sites/{SITE_ID}/band-steering"

    @staticmethod
    def _site_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/wifi/band-steering"

    @staticmethod
    def _preview_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/wifi/band-steering-preview"

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
        approval = sign_approval(
            self.operator_key, operation="band-steering", plan_id=preview["plan_id"],
            plan_digest=preview["approval_request"]["digest"], operator_id=OPERATOR_ID,
            expires_at=now + 120, now=now)
        return {"approval": approval}

    def test_authenticated_get_unknown_site_and_unknown_response_fields_fail_closed(self) -> None:
        status, error = self.request("GET", self._site_path())
        self.assertEqual(status, 401)
        self.assertEqual(error["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, result = self.request("GET", self._site_path(), token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], {"mode": 0})
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])

        before = len(self.transport_calls)
        status, unknown = self.request("GET", self._site_path("c" * 24), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(unknown["error"], "site_ref_unknown")
        self.assertEqual(len(self.transport_calls), before)

        self.extra_get_field = True
        status, invalid = self.request("GET", self._site_path(), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(invalid["error"], "openapi_response_invalid")

    def test_preview_requires_confirmation_and_approval_then_reads_back_once(self) -> None:
        status, unauth = self.request("POST", self._preview_path(),
                                      body={"changes": {"mode": 1}, "disruption_confirmed": True})
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        for body in ({"changes": {"mode": 1}},
                     {"changes": {"mode": 1}, "disruption_confirmed": False},
                     {"changes": {"mode": True}, "disruption_confirmed": True},
                     {"changes": {"mode": 3}, "disruption_confirmed": True},
                     {"changes": {"mode": 1, "extra": 0}, "disruption_confirmed": True},
                     {"changes": {"mode": 1}, "disruption_confirmed": True, "extra": 0}):
            status, error = self.request("POST", self._preview_path(), token=self.token, body=body)
            self.assertEqual(status, 400, body)
            self.assertEqual(error["status"], "error")
            self.assertFalse(any(call[0] == "PATCH" for call in self.transport_calls))

        status, preview = self.request(
            "POST", self._preview_path(), token=self.token,
            body={"changes": {"mode": 2}, "disruption_confirmed": True})
        self.assertEqual(status, 200)
        self.assertEqual(preview["before"], {"mode": 0})
        self.assertEqual(preview["target"], {"mode": 2})
        self.assertIn("interrupt_clients", preview["warning"])
        self.assertEqual(preview["approval_request"]["operation"], "band-steering")
        apply_path = f"/v1/band-steering-plans/{preview['plan_id']}/apply"

        status, unauth_apply = self.request("POST", apply_path, body={})
        self.assertEqual(status, 401)
        self.assertEqual(unauth_apply["error"], "unauthorized")
        self.assertFalse(any(call[0] == "PATCH" for call in self.transport_calls))

        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, no_approval = self.request("POST", apply_path, token=self.token, body={})
        self.assertEqual(status, 409)
        self.assertEqual(no_approval["error"], "operator_approval_required")
        self.assertFalse(any(call[0] == "PATCH" for call in self.transport_calls))

        status, applied = self.request("POST", apply_path, token=self.token,
                                       body=self.approval_body(preview))
        self.assertEqual(status, 200)
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["before"], {"mode": 0})
        self.assertEqual(applied["after"], {"mode": 2})
        self.assertEqual([call[0] for call in self.transport_calls], ["GET", "GET", "GET", "PATCH", "GET"])
        patch_call = next(call for call in self.transport_calls if call[0] == "PATCH")
        self.assertEqual(patch_call[1], self._upstream_path())
        self.assertEqual(json.loads(patch_call[2]), {"bandSteeringForMultiBand": {"mode": 2}})

        status, replay = self.request("POST", apply_path, token=self.token,
                                      body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PATCH"]), 1)

    def test_preview_accepts_all_three_documented_modes(self) -> None:
        for mode in (0, 1, 2):
            with self.subTest(mode=mode):
                self.mode = (mode + 1) % 3
                status, preview = self.request(
                    "POST", self._preview_path(), token=self.token,
                    body={"changes": {"mode": mode}, "disruption_confirmed": True})
                self.assertEqual(status, 200)
                self.assertEqual(preview["target"], {"mode": mode})
        self.assertFalse(any(call[0] == "PATCH" for call in self.transport_calls))

    def test_stale_change_and_controller_failure_are_not_replayed_and_recover_from_journal(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, stale_preview = self.request(
            "POST", self._preview_path(), token=self.token,
            body={"changes": {"mode": 1}, "disruption_confirmed": True})
        self.assertEqual(status, 200)
        stale_path = f"/v1/band-steering-plans/{stale_preview['plan_id']}/apply"
        self.mode = 2  # External change between preview and apply.
        status, stale = self.request("POST", stale_path, token=self.token,
                                    body=self.approval_body(stale_preview))
        self.assertEqual(status, 409)
        self.assertEqual(stale["error"], "state_changed")
        self.assertFalse(any(call[0] == "PATCH" for call in self.transport_calls))

        self.mode = 0
        status, failed_preview = self.request(
            "POST", self._preview_path(), token=self.token,
            body={"changes": {"mode": 2}, "disruption_confirmed": True})
        self.assertEqual(status, 200)
        apply_path = f"/v1/band-steering-plans/{failed_preview['plan_id']}/apply"
        self.apply_then_fail = True  # Ambiguous timeout after the controller accepted PATCH.
        status, failed = self.request("POST", apply_path, token=self.token,
                                     body=self.approval_body(failed_preview))
        self.assertEqual(status, 409)
        self.assertEqual(failed["error"], "change_in_doubt")
        patch_calls = [call for call in self.transport_calls if call[0] == "PATCH"]
        self.assertEqual(len(patch_calls), 1)

        status, replay = self.request("POST", apply_path, token=self.token,
                                      body=self.approval_body(failed_preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PATCH"]), 1)

        # Reopen the real persistent journal through the shared manager route.
        runtime = main._JOURNAL_RUNTIME
        self.assertIsNotNone(runtime)
        runtime.close()
        main._JOURNAL_RUNTIME = None
        main._BAND_STEERING_PLANS = None
        status, items = self.request("GET", "/v1/change-plans/band-steering/in-doubt",
                                     token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(len(items["items"]), 1)
        self.assertEqual(items["items"][0]["plan_id"], failed_preview["plan_id"])
        self.assertEqual(items["items"][0]["state"], "in_doubt")
        status, recovered_replay = self.request("POST", apply_path, token=self.token,
                                                body=self.approval_body(failed_preview))
        self.assertEqual(status, 409)
        self.assertEqual(recovered_replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PATCH"]), 1)

    def test_controller_allowlist_pins_path_method_and_body(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id-file", "secret-file",
            cert_sha256="a" * 64))
        accepted_path = self._upstream_path()
        connection_error = OpenApiError("connection_reached")
        with patch.object(client, "_connection", side_effect=connection_error):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", accepted_path, token="token")
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                client._request_json("PATCH", accepted_path,
                                     body=b'{"bandSteeringForMultiBand":{"mode":1}}', token="token")
            client._write_dispatch_guard = lambda: None
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("PATCH", accepted_path,
                                     body=b'{"bandSteeringForMultiBand":{"mode":1}}', token="token")
            forbidden = (
                ("GET", accepted_path + "?raw=true", None),
                ("GET", self._upstream_path("foreign_controller"), None),
                ("POST", accepted_path, b'{"bandSteeringForMultiBand":{"mode":1}}'),
                ("PATCH", accepted_path, b'{"mode":1}'),
                ("PATCH", accepted_path, b'{"bandSteeringForMultiBand":{"mode":true}}'),
                ("PATCH", accepted_path, b'{"bandSteeringForMultiBand":{"mode":3}}'),
                ("PATCH", accepted_path, b'{"bandSteeringForMultiBand":{"mode":1,"extra":0}}'),
                ("PATCH", accepted_path, b'{"bandSteeringForMultiBand":{"mode":1},"extra":0}'),
                ("PATCH", accepted_path, b'{"bandSteeringForMultiBand":{"mode":1},"bandSteeringForMultiBand":{"mode":2}}'),
                ("PUT", accepted_path, b'{"bandSteeringForMultiBand":{"mode":1}}'),
            )
            for method, path, body in forbidden:
                with self.subTest(method=method, path=path, body=body), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, body=body, token="token")

    def test_credentials_and_raw_ids_are_not_logged(self) -> None:
        status, preview = self.request(
            "POST", self._preview_path(), token=self.token,
            body={"changes": {"mode": 1}, "disruption_confirmed": True})
        self.assertEqual(status, 200)
        for secret in (SITE_REF, SITE_ID, self.token, self.operator_key.hex(), preview["plan_id"]):
            self.assertNotIn(secret, self.logs.getvalue())


if __name__ == "__main__":
    unittest.main()
