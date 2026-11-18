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
from pathlib import Path
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig


TOKEN = "roaming-integration-caller-token-0123456789abcdef"
SITE_REF = "a" * 24


class RoamingSettingsHttpIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_path = Path(self.temp.name) / "caller-token"
        self.token_path.write_text(TOKEN, encoding="ascii")
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "known-site-id"
        self.payload: object = {"roaming": {
            "fastRoamingEnable": True,
            "aiRoamingEnable": False,
            "dualBand11kReportEnable": True,
            "forceDisassociationEnable": False,
            "nonStickRoamingEnable": True,
        }}
        self.upstream: list[tuple[str, str, object]] = []
        self.logs = io.StringIO()

        def fake_request(method: str, path: str, *, token: str | None = None, **_kwargs):
            self.upstream.append((method, path, token))
            return {"result": self.payload}

        self.request_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.request_patch.start()
        self.access_patch = patch.object(self.client, "_access_token", return_value="synthetic-access-token")
        self.access_patch.start()
        self.env = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": str(self.token_path)})
        self.env.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.print_patch = patch.object(builtins, "print", lambda *args, **_kwargs:
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
        self.env.stop()
        self.access_patch.stop()
        self.request_patch.stop()
        self.temp.cleanup()

    def request(self, method: str, path: str, *, authenticated: bool = True):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + TOKEN} if authenticated else {}
        conn.request(method, path, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        conn.close()
        return response.status, value

    def test_auth_known_site_and_fixed_get_redact_sensitive_values(self) -> None:
        path = f"/v1/sites/{SITE_REF}/wifi/roaming"
        status, result = self.request("GET", path, authenticated=False)
        self.assertEqual(status, 401)
        self.assertEqual(result["error"], "unauthorized")
        self.assertEqual(self.upstream, [])

        status, result = self.request("GET", path)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], self.payload["roaming"])
        self.assertFalse(result["partial"])
        self.assertEqual(self.upstream, [(
            "GET", "/openapi/v1/ctrl/sites/known-site-id/roaming",
            "synthetic-access-token")])
        self.assertTrue(all(method == "GET" for method, _path, _token in self.upstream))
        self.assertNotIn("known-site-id", json.dumps(result))

    def test_unknown_or_invalid_site_and_unmapped_method_or_path_do_not_read_upstream(self) -> None:
        status, _result = self.request("GET", f"/v1/sites/{'b' * 24}/wifi/roaming")
        self.assertNotEqual(status, 200)
        status, _result = self.request("GET", "/v1/sites/not-a-reference/wifi/roaming")
        self.assertNotEqual(status, 200)
        status, _result = self.request("POST", f"/v1/sites/{SITE_REF}/wifi/roaming")
        self.assertNotEqual(status, 200)
        status, _result = self.request("GET", f"/v1/sites/{SITE_REF}/wifi/roaming/extra")
        self.assertNotEqual(status, 200)
        self.assertEqual(self.upstream, [])

    def test_partial_and_malformed_field_responses_do_not_claim_support(self) -> None:
        self.payload = {"roaming": {
            "fastRoamingEnable": True,
            "aiRoamingEnable": "invalid-bool",
            "privateProfileId": "private-id-value",
        }}
        status, result = self.request("GET", f"/v1/sites/{SITE_REF}/wifi/roaming")
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], {"fastRoamingEnable": True})
        self.assertTrue(result["partial"])
        encoded = json.dumps(result)
        for private in ("privateProfileId", "private-id-value", "invalid-bool"):
            self.assertNotIn(private, encoded)
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "roaming_settings")["runtime_evidence"][-1]
        self.assertEqual(evidence["result"], "success")
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["observation"], "response_partial")
        self.assertEqual(evidence["hardware_support_state"], "unknown")
        self.assertEqual(evidence["firmware_support_state"], "unknown")
        self.assertNotIn("private-id-value", json.dumps(evidence))

        self.payload = None
        status, error = self.request("GET", f"/v1/sites/{SITE_REF}/wifi/roaming")
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_response_invalid")
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "roaming_settings")["runtime_evidence"][-1]
        self.assertEqual(evidence["result"], "failure")
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertNotIn("private-id-value", json.dumps(evidence))

    def test_partial_unknown_fields_and_logs_never_echo_names_or_ids(self) -> None:
        self.payload = {"roaming": {"fastRoamingEnable": False},
                        "privateSiteName": "secret-site"}
        status, result = self.request("GET", f"/v1/sites/{SITE_REF}/wifi/roaming")
        self.assertEqual(status, 200)
        self.assertTrue(result["partial"])
        rendered = json.dumps(result) + self.logs.getvalue()
        for private in ("secret-site", "privateSiteName", "known-site-id"):
            self.assertNotIn(private, rendered)


if __name__ == "__main__":
    unittest.main()
