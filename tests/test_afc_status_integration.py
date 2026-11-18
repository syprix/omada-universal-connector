from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


TOKEN = "afc-status-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
DEVICE_REF = "b" * 24
OTHER_DEVICE_REF = "c" * 24
SITE_ID = "known-site-id"
AP_MAC = "00:11:22:33:44:55"


class AfcStatusHttpIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_path = os.path.join(self.temp.name, "caller-token")
        with open(self.token_path, "w", encoding="ascii") as handle:
            handle.write(TOKEN)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.client._device_macs_by_site_ref[SITE_REF] = {DEVICE_REF: AP_MAC}
        self.result: object = {
            "status": True, "expirationTimeSec": 1_700_000_123,
            "lastResponse": False, "lastResponseTimeSec": 1_600_000_456,
            "errCode": -12, "errMain": 3, "errDetail": -4,
            "processing": False, "available6g": True,
        }
        self.calls: list[tuple[str, str, str | None]] = []
        self.logs = io.StringIO()

        def fake_request(method: str, path: str, *, token: str | None = None, **_kwargs):
            self.calls.append((method, path, token))
            return {"result": self.result}

        self.request_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.request_patch.start()
        self.access_patch = patch.object(
            self.client, "_access_token", return_value="synthetic-upstream-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_path})
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.print_patch = patch.object(
            builtins, "print", lambda *args, **_kwargs:
            self.logs.write(" ".join(map(str, args)) + "\n"))
        self.print_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.print_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.request_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def _upstream_path(controller_id: str = "ctrl", site_id: str = SITE_ID,
                       mac: str = AP_MAC) -> str:
        return f"/openapi/v1/{controller_id}/sites/{site_id}/aps/{mac}/afc"

    @staticmethod
    def _path(site_ref: str = SITE_REF, device_ref: str = DEVICE_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/{device_ref}/afc/status"

    def request(self, method: str, path: str, *, authenticated: bool = True):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + TOKEN} if authenticated else {}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        connection.close()
        return response.status, value

    def _evidence(self) -> dict[str, object]:
        item = next(item for item in self.client.capabilities()["items"]
                    if item["operation"] == "ap_afc_status")
        self.assertEqual(item["support_state"], "unknown")
        return item["runtime_evidence"][-1]

    def test_auth_site_binding_exact_fixed_get_and_redacted_projection(self) -> None:
        status, unauthorized = self.request("GET", self._path(), authenticated=False)
        self.assertEqual(status, 401)
        self.assertEqual(unauthorized["error"], "unauthorized")
        self.assertEqual(self.calls, [])

        status, result = self.request("GET", self._path())
        self.assertEqual(status, 200)
        self.assertEqual(result["resource"], "ap_afc_status")
        self.assertEqual(result["site_ref"], SITE_REF)
        self.assertEqual(result["device_ref"], DEVICE_REF)
        self.assertEqual(result["data"]["expirationTimeSec"], 1_700_000_123)
        self.assertEqual(result["data"]["lastResponseTimeSec"], 1_600_000_456)
        self.assertEqual(result["data"]["errCode"], -12)
        self.assertFalse(result["partial"])
        self.assertEqual(self.calls, [(
            "GET", self._upstream_path(), "synthetic-upstream-token")])
        evidence = self._evidence()
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["response_shape_state"], "response_shape_supported")
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["hardware_support_state"], "unknown")
        self.assertEqual(evidence["firmware_support_state"], "unknown")
        rendered = json.dumps(result) + json.dumps(evidence) + self.logs.getvalue()
        for private in (SITE_ID, AP_MAC, "synthetic-upstream-token", "unused-secret"):
            self.assertNotIn(private, rendered)

    def test_site_or_ap_not_in_inventory_is_rejected_without_upstream_read(self) -> None:
        for path in (self._path("d" * 24), self._path(SITE_REF, OTHER_DEVICE_REF),
                     self._path("not-a-ref", DEVICE_REF)):
            with self.subTest(path=path):
                status, _result = self.request("GET", path)
                self.assertNotEqual(status, 200)
        self.assertEqual(self.calls, [])

    def test_partial_unknown_and_invalid_values_are_redacted_and_capability_unknown(self) -> None:
        self.result = {
            "status": True,
            "expirationTimeSec": True,
            "errCode": 2**31,
            "privateErrorText": "secret-detail",
            "rawApMac": AP_MAC,
        }
        status, result = self.request("GET", self._path())
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], {"status": True})
        self.assertTrue(result["partial"])
        self.assertIn("expirationTimeSec", result["omitted_fields"])
        self.assertIn("errCode", result["omitted_fields"])
        self.assertIn("unknown_fields", result["omitted_fields"])
        evidence = self._evidence()
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["observation"], "response_partial")
        rendered = json.dumps(result) + json.dumps(evidence) + self.logs.getvalue()
        for private in ("privateErrorText", "secret-detail", "rawApMac", AP_MAC):
            self.assertNotIn(private, rendered)

        self.result = None
        status, error = self.request("GET", self._path())
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_response_invalid")
        evidence = self._evidence()
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["result"], "failure")

    def test_only_exact_get_route_is_exposed(self) -> None:
        before = len(self.calls)
        for method, path in (
            ("POST", self._path()),
            ("PUT", self._path()),
            ("GET", self._path() + "/extra"),
            ("GET", self._path() + "?raw=true"),
        ):
            with self.subTest(method=method, path=path):
                status, _result = self.request(method, path)
                self.assertNotEqual(status, 200)
        self.assertEqual(len(self.calls), before)

    def test_controller_allowlist_rejects_other_methods_paths_and_controller_ids(self) -> None:
        valid = self._upstream_path()
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        connection_error = OpenApiError("connection_reached")
        with patch.object(client, "_connection", side_effect=connection_error):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", valid, token="token")
            rejected = (
                ("POST", valid, None),
                ("PUT", valid, b'{"enable":true}'),
                ("GET", valid + "?unexpected=1", None),
                ("GET", self._upstream_path("other-controller"), None),
            )
            for method, path, body in rejected:
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, body=body, token="token")


if __name__ == "__main__":
    unittest.main()
