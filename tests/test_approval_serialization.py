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


TOKEN = "approval-serialization-token-0123456789abcdef"
REFERENCE_KEY = b"r" * 32
APPROVAL_KEY = b"o" * 32
SITE = "a" * 24
SWITCH = "b" * 24
OPERATOR = "op_" + "1" * 24
PORT = 7


class BlockingFakeClient:
    def __init__(self, reference_key_file: str):
        self.config = SimpleNamespace(reference_key_file=reference_key_file,
                                      base_url="https://controller.example",
                                      controller_id="serialization-controller")
        self._ref_key = REFERENCE_KEY
        self.status = {"status": 1}
        self.reads = 0
        self.writes: list[dict[str, int]] = []
        self.write_entered = threading.Event()
        self.release_write = threading.Event()

    def read_switch_port_status(self, _site: str, _switch: str, _port: int):
        self.reads += 1
        return {"status": "ok", "resource": "switch_port_status",
                "data": dict(self.status)}

    def put_switch_port_status(self, _site: str, _switch: str, _port: int,
                               body: dict[str, int]):
        self.writes.append(dict(body))
        self.write_entered.set()
        if not self.release_write.wait(5):
            raise TimeoutError("local test write release timed out")
        self.status = dict(body)


class ApprovalSerializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.token_file = root / "caller-token"
        self.token_file.write_text(TOKEN, encoding="ascii")
        os.chmod(self.token_file, 0o600)
        reference_key_file = root / "reference-key"
        reference_key_file.write_bytes(REFERENCE_KEY)
        os.chmod(reference_key_file, 0o600)
        self.operator_key_file = root / "operator-key"
        self.operator_key_file.write_bytes(APPROVAL_KEY)
        os.chmod(self.operator_key_file, 0o600)
        self.journal_dir = root / "journal"
        self.journal_dir.mkdir(mode=0o700)
        os.chmod(self.journal_dir, 0o700)

        self.client = BlockingFakeClient(str(reference_key_file))
        self.env = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": str(self.token_file),
            "OMADA_REFERENCE_KEY_FILE": str(reference_key_file),
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": str(self.operator_key_file),
            "OMADA_CHANGE_JOURNAL_DIR": str(self.journal_dir),
            "OMADA_ENABLE_WRITES": "true",
        })
        self.env.start()
        self._reset_app_globals()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()

        self.second_handler_entered = threading.Event()
        outer = self

        class TrackingHandler(main.Handler):
            def do_POST(handler_self):
                if handler_self.path == outer.second_apply_path:
                    outer.second_handler_entered.set()
                super().do_POST()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TrackingHandler)
        self.server.daemon_threads = True
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.second_apply_path = ""

    @staticmethod
    def _reset_app_globals() -> None:
        runtime = main._JOURNAL_RUNTIME
        if runtime is not None:
            runtime.close()
        main._JOURNAL_RUNTIME = None
        main._PORT_STATUS_PLANS = None
        main._CONSUMED_APPROVALS.clear()
        main._ACTIVE_APPROVAL = None

    def tearDown(self) -> None:
        self.client.release_write.set()
        self.server.shutdown()
        self.server_thread.join(timeout=2)
        self.server.server_close()
        self._reset_app_globals()
        self.client_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    def request(self, method: str, path: str, body: dict[str, object] | None = None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=4)
        headers = {"Authorization": "Bearer " + TOKEN}
        payload = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body or {}, separators=(",", ":")).encode()
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        return response.status, json.loads(raw)

    @staticmethod
    def preview_path() -> str:
        return f"/v1/sites/{SITE}/switches/{SWITCH}/ports/{PORT}/status-preview"

    @staticmethod
    def apply_path(plan_id: str) -> str:
        return f"/v1/switch-port-status-plans/{plan_id}/apply"

    def approve(self, preview: dict[str, object]) -> dict[str, object]:
        request = preview["approval_request"]
        assert isinstance(request, dict)
        now = int(time.time())
        return sign_approval(
            APPROVAL_KEY, operation="switch-port-status",
            plan_id=str(request["plan_id"]), plan_digest=str(request["digest"]),
            operator_id=OPERATOR, expires_at=now + 120, now=now)

    def test_serializes_http_applies_until_first_send_finishes(self) -> None:
        status1, preview1 = self.request("POST", self.preview_path(), {
            "changes": {"status": 0}, "disruption_confirmed": True})
        self.assertEqual(status1, 200)
        plan1 = str(preview1["plan_id"])
        approval1 = self.approve(preview1)

        # Prepare an independent plan and approval against the opposite state.
        self.client.status = {"status": 0}
        status2, preview2 = self.request("POST", self.preview_path(), {
            "changes": {"status": 1}, "disruption_confirmed": True})
        self.assertEqual(status2, 200)
        plan2 = str(preview2["plan_id"])
        approval2 = self.approve(preview2)
        self.assertNotEqual(plan1, plan2)
        self.assertNotEqual(approval1["plan_digest"], approval2["plan_digest"])
        self.client.status = {"status": 1}

        self.second_apply_path = self.apply_path(plan2)
        first_result: list[tuple[int, dict[str, object]]] = []
        first = threading.Thread(target=lambda: first_result.append(self.request(
            "POST", self.apply_path(plan1), {"approval": approval1})), daemon=True)
        first.start()
        self.assertTrue(self.client.write_entered.wait(2), "first fake write did not start")
        first_context = dict(main._ACTIVE_APPROVAL or {})
        reads_at_block = self.client.reads
        writes_at_block = list(self.client.writes)
        self.assertEqual(writes_at_block, [{"status": 0}])
        self.assertEqual(first_context.get("kind"), "switch-port-status")

        second_result: list[tuple[int, dict[str, object]]] = []
        second = threading.Thread(target=lambda: second_result.append(self.request(
            "POST", self.apply_path(plan2), {"approval": approval2})), daemon=True)
        second.start()
        self.assertTrue(self.second_handler_entered.wait(2), "second HTTP handler did not start")
        # The second handler has entered do_POST, but must wait for the shared lock.
        time.sleep(0.1)
        self.assertEqual(self.client.reads, reads_at_block)
        self.assertEqual(self.client.writes, writes_at_block)
        self.assertEqual(main._ACTIVE_APPROVAL, first_context)
        self.assertFalse(second_result)

        self.client.release_write.set()
        first.join(timeout=3)
        second.join(timeout=3)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(first_result[0][0], 200)
        self.assertEqual(second_result[0][0], 200)
        self.assertEqual(self.client.writes, [{"status": 0}, {"status": 1}])


if __name__ == "__main__":
    unittest.main()
