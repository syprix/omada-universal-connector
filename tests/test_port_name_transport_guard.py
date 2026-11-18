from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from tests.test_port_name_integration import (
    NEW_NAME, OLD_NAME, TOKEN, PortNameIntegrationTests, SITE_ID, SWITCH_MAC,
)


class _Response:
    status = 200

    @staticmethod
    def read(_maximum: int) -> bytes:
        return b'{"errorCode":0,"result":null}'

    @staticmethod
    def getheader(_name: str, default: str = "") -> str:
        return "application/json" if not default else default


class _Connection:
    def __init__(self, order: list[str]):
        self.order = order
        self.calls: list[tuple[str, str, bytes | None, dict[str, str]]] = []

    def request(self, method: str, path: str, *, body=None, headers=None) -> None:
        self.order.append("request")
        self.calls.append((method, path, body, headers or {}))

    @staticmethod
    def getresponse():
        return _Response()

    def close(self) -> None:
        pass


class PortNameRequestJsonAllowlistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.path = (f"/openapi/v1/ctrl/sites/{SITE_ID}/switches/"
                     f"{SWITCH_MAC}/ports/7/name")
        self.body = json.dumps({"name": NEW_NAME}, separators=(",", ":")).encode()
        self.connection = _Connection([])
        self.connection_patch = patch.object(self.client, "_connection",
                                             side_effect=self._connection)
        self.connection_patch.start()

    def tearDown(self) -> None:
        self.connection_patch.stop()

    def _connection(self):
        self.connection.order.append("connect")
        return self.connection

    def test_wrong_method_and_controller_are_rejected_before_connection(self) -> None:
        self.client._write_dispatch_guard = lambda: None
        for method, path in (
                ("PATCH", self.path),
                ("PUT", self.path.replace("/openapi/v1/ctrl/", "/openapi/v1/other/"))):
            with self.subTest(method=method, path=path), self.assertRaises(OpenApiError) as raised:
                self.client._request_json(method, path, body=self.body, token="fake")
            self.assertEqual(raised.exception.code, "openapi_path_rejected")
        self.assertEqual(self.connection.calls, [])
        self.assertEqual(self.connection.order, [])

    def test_foreign_body_field_and_duplicate_json_keys_are_rejected(self) -> None:
        self.client._write_dispatch_guard = lambda: None
        invalid_bodies = (
            b'{"name":"valid label","private":"leak"}',
            b'{"name":"first","name":"second"}',
        )
        for body in invalid_bodies:
            with self.subTest(body=body), self.assertRaises(OpenApiError) as raised:
                self.client._request_json("PUT", self.path, body=body, token="fake")
            self.assertEqual(raised.exception.code, "openapi_path_rejected")
        self.assertEqual(self.connection.calls, [])

    def test_dispatch_guard_is_checked_after_connect_and_immediately_before_request(self) -> None:
        self.client._write_dispatch_guard = lambda: self.connection.order.append("guard")
        self.client._request_json("PUT", self.path, body=self.body, token="fake")
        self.assertEqual(self.connection.order, ["connect", "guard", "request"])
        self.assertEqual(len(self.connection.calls), 1)
        method, path, body, _headers = self.connection.calls[0]
        self.assertEqual((method, path, body), ("PUT", self.path, self.body))

    def test_missing_or_rejecting_dispatch_guard_prevents_request(self) -> None:
        with self.assertRaises(OpenApiError) as missing:
            self.client._request_json("PUT", self.path, body=self.body, token="fake")
        self.assertEqual(missing.exception.code, "operator_approval_required")
        self.assertEqual(self.connection.order, [])

        self.client._write_dispatch_guard = lambda: (_ for _ in ()).throw(
            RuntimeError("approval expired"))
        with self.assertRaises(RuntimeError):
            self.client._request_json("PUT", self.path, body=self.body, token="fake")
        self.assertEqual(self.connection.order, ["connect"])
        self.assertEqual(self.connection.calls, [])


class PortNameReadbackMismatchTests(unittest.TestCase):
    def test_successful_put_with_mismatched_readback_is_in_doubt_and_never_replayed(self) -> None:
        fixture = PortNameIntegrationTests(
            "test_approved_apply_is_single_put_readback_and_secret_free_outside_preview")
        fixture.setUp()
        try:
            original_side_effect = fixture.client._request_json.side_effect

            def mismatch_after_put(method, path, body=None, token=None):
                result = original_side_effect(method, path, body=body, token=token)
                if method == "PUT":
                    fixture.port_name = "unrelated current name"
                return result

            fixture.client._request_json.side_effect = mismatch_after_put
            os.environ["OMADA_ENABLE_WRITES"] = "true"
            preview = fixture.preview()
            apply_path = f"/v1/switch-port-name-plans/{preview['plan_id']}/apply"
            status, result = fixture.request(
                "POST", apply_path, token=TOKEN,
                body=fixture.approval_body(preview))
            fixture.assertEqual(status, 409)
            fixture.assertEqual(result["error"], "change_in_doubt")
            fixture.assertEqual(len(fixture.put_calls), 1)

            # Approval summary refuses a consumed in-doubt plan before dispatch.
            status, replay = fixture.request(
                "POST", apply_path, token=TOKEN,
                body=fixture.approval_body(preview))
            fixture.assertEqual(status, 409)
            fixture.assertEqual(replay["error"], "plan_unavailable")
            fixture.assertEqual(len(fixture.put_calls), 1)

            status, inspect = fixture.request(
                "GET", f"/v1/change-plans/switch-port-name/{preview['plan_id']}",
                token=TOKEN)
            fixture.assertEqual(status, 200, inspect)
            fixture.assertEqual(inspect["state"], "in_doubt")
            rendered = json.dumps(inspect) + fixture.logs.getvalue()
            fixture.assertNotIn(OLD_NAME, rendered)
            fixture.assertNotIn(NEW_NAME, rendered)
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
