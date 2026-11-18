from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import main
from app.operator_approval import sign_approval


TOKEN = "switch-port-status-caller-token-0123456789abcdef"
KEY = b"s" * 32
URL = "https://controller.example:8043"
CONTROLLER = "status-controller"
SITE = "a" * 24
SWITCH = "b" * 24
PORT = 7


class SimulatedClient:
    def __init__(self, reference_key_file: str):
        self.config = SimpleNamespace(reference_key_file=reference_key_file,
                                      base_url=URL, controller_id=CONTROLLER)
        self._ref_key = KEY
        self.port_status = {"status": 1}
        self.write_attempts: list[dict[str, int]] = []
        self.fail_write = False
        self.read_attempts = 0

    def read_switch_port_status(self, _site: str, _switch: str, _port: int):
        self.read_attempts += 1
        return {"status": "ok", "resource": "switch_port_status",
                "data": dict(self.port_status)}

    def put_switch_port_status(self, _site: str, _switch: str, _port: int,
                               body: dict[str, int]):
        self.write_attempts.append(dict(body))
        if self.fail_write:
            raise TimeoutError("simulated timeout")
        self.port_status = dict(body)


class SwitchPortStatusHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.token_file = self.root / "caller-token"
        self.token_file.write_text(TOKEN, encoding="ascii")
        self.key_file = self.root / "reference-key"
        self.key_file.write_bytes(KEY)
        os.chmod(self.key_file, 0o600)
        self.operator_key = b"o" * 32
        self.operator_key_file = self.root / "operator-approval-key"
        self.operator_key_file.write_bytes(self.operator_key)
        os.chmod(self.operator_key_file, 0o600)
        self.client = SimulatedClient(str(self.key_file))
        self.env = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": str(self.token_file),
            "OMADA_ENABLE_WRITES": "false",
            "OMADA_CHANGE_JOURNAL_DIR": "",
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": str(self.operator_key_file),
        })
        self.env.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self._reset_globals()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @staticmethod
    def _reset_globals():
        for name in ("_RADIO_PLANS", "_DNS_CACHE_PLANS", "_SSID_PLANS",
                     "_GATEWAY_IPV6_PLANS", "_POE_PLANS", "_PORT_STATUS_PLANS"):
            setattr(main, name, None)
        main._JOURNAL_RUNTIME = None
        main._CONSUMED_APPROVALS.clear()
        main._ACTIVE_APPROVAL = None

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        if main._JOURNAL_RUNTIME is not None:
            main._JOURNAL_RUNTIME.close()
        self._reset_globals()
        self.client_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    def enable_journal(self) -> Path:
        folder = self.root / "journal"
        folder.mkdir(mode=0o700)
        os.chmod(folder, 0o700)
        os.environ["OMADA_CHANGE_JOURNAL_DIR"] = str(folder)
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        return folder

    @staticmethod
    def status_path() -> str:
        return f"/v1/sites/{SITE}/switches/{SWITCH}/ports/{PORT}/status"

    @staticmethod
    def preview_path() -> str:
        return f"/v1/sites/{SITE}/switches/{SWITCH}/ports/{PORT}/status-preview"

    def request(self, method: str, path: str, body=None, *, authorized=True):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {}
        payload = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body if body is not None else {}).encode()
        if authorized:
            headers["Authorization"] = "Bearer " + TOKEN
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        result = json.loads(response.read())
        conn.close()
        return response.status, result

    def preview(self, target=0):
        return self.request("POST", self.preview_path(), {
            "changes": {"status": target}, "disruption_confirmed": True})

    def approval_body(self, preview: dict[str, object]) -> dict[str, object]:
        request = preview["approval_request"]
        return {"approval": sign_approval(
            self.operator_key, operation="switch-port-status", plan_id=preview["plan_id"],
            plan_digest=request["digest"], operator_id="op_" + "4" * 24,
            expires_at=int(time.time()) + 120)}

    def apply(self, plan_id: str, preview: dict[str, object] | None = None):
        body = self.approval_body(preview) if preview is not None else {}
        return self.request("POST", f"/v1/switch-port-status-plans/{plan_id}/apply", body)

    def test_auth_protects_status_preview_apply_and_in_doubt(self):
        self.enable_journal()
        for method, path, body in (
            ("GET", self.status_path(), None),
            ("POST", self.preview_path(), {"changes": {"status": 0},
                                             "disruption_confirmed": True}),
            ("GET", "/v1/change-plans/switch-port-status/in-doubt", None),
        ):
            with self.subTest(method=method, path=path):
                status, result = self.request(method, path, body, authorized=False)
                self.assertEqual(status, 401)
                self.assertEqual(result["error"], "unauthorized")
        self.assertEqual(self.client.write_attempts, [])

    def test_get_status_uses_only_simulated_client(self):
        status, result = self.request("GET", self.status_path())
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], {"status": 1})
        self.assertEqual(self.client.read_attempts, 1)
        self.assertEqual(self.client.write_attempts, [])

    def test_default_off_allows_preview_but_blocks_apply_before_write(self):
        status, preview = self.preview()
        self.assertEqual(status, 200)
        status, result = self.apply(preview["plan_id"])
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "writes_disabled")
        self.assertEqual(self.client.write_attempts, [])

    def test_preview_requires_explicit_disruption_confirmation(self):
        self.enable_journal()
        status, result = self.request("POST", self.preview_path(), {
            "changes": {"status": 0}, "disruption_confirmed": False})
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "disruption_confirmation_required")
        status, result = self.request("POST", self.preview_path(), {
            "changes": {"status": 0}})
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "request_invalid")
        self.assertEqual(self.client.write_attempts, [])

    def test_journalled_apply_returns_before_after_and_blocks_replay(self):
        self.enable_journal()
        status, preview = self.preview(target=0)
        self.assertEqual(status, 200)
        status, applied = self.apply(preview["plan_id"], preview)
        self.assertEqual(status, 200)
        self.assertEqual(applied["before"], {"status": 1})
        self.assertEqual(applied["after"], {"status": 0})
        self.assertEqual(self.client.write_attempts, [{"status": 0}])
        status, replay = self.apply(preview["plan_id"], preview)
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(self.client.write_attempts, [{"status": 0}])

    def test_stale_state_is_rejected_without_dispatch(self):
        self.enable_journal()
        status, preview = self.preview(target=0)
        self.assertEqual(status, 200)
        self.client.port_status = {"status": 0}
        status, result = self.apply(preview["plan_id"], preview)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "state_changed")
        self.assertEqual(self.client.write_attempts, [])

    def test_uncertain_write_recovers_in_doubt_and_close_never_replays(self):
        self.enable_journal()
        self.client.fail_write = True
        status, preview = self.preview(target=0)
        self.assertEqual(status, 200)
        plan_id = preview["plan_id"]
        status, result = self.apply(plan_id, preview)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "change_in_doubt")
        self.assertEqual(self.client.write_attempts, [{"status": 0}])

        # Simulate a process restart: release the real lock and force fresh recovery.
        main._JOURNAL_RUNTIME.close()
        self._reset_globals()
        status, listed = self.request("GET", "/v1/change-plans/switch-port-status/in-doubt")
        self.assertEqual(status, 200)
        self.assertEqual([item["plan_id"] for item in listed["items"]], [plan_id])
        status, inspected = self.request("GET", f"/v1/change-plans/switch-port-status/{plan_id}")
        self.assertEqual(status, 200)
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertEqual(inspected["current_observation"]["data"], {"status": 1})
        status, replay = self.apply(plan_id, preview)
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(self.client.write_attempts, [{"status": 0}])

        status, closed = self.request("POST", f"/v1/change-plans/switch-port-status/{plan_id}/close",
                                      {"confirmation": "outcome_unknown_no_retry"})
        self.assertEqual(status, 200)
        self.assertEqual(closed["state"], "closed_outcome_unknown")
        self.assertEqual(self.client.write_attempts, [{"status": 0}])


if __name__ == "__main__":
    unittest.main()
