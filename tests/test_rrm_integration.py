from __future__ import annotations

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


TOKEN = "rrm-integration-caller-token-0123456789abcdef"
SITE_REF = "a" * 24


class RrmSettingsHttpIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_path = Path(self.temp.name) / "caller-token"
        self.token_path.write_text(TOKEN, encoding="ascii")
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "known-site-id"
        self.upstream: list[tuple[str, str, object]] = []
        self.payload: object = {
            "mode": 1, "timeRangeEnable": True, "resource": 2,
            "timeRangeAction": 0, "timeRangeId": "private-range-id",
            "privateExtension": "private-controller-value",
        }

        def fake_request(method: str, path: str, *, token: str | None = None,
                         **_kwargs):
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
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.client_patch.stop()
        self.env.stop()
        self.access_patch.stop()
        self.request_patch.stop()
        self.temp.cleanup()

    def get(self, path: str, *, authenticated: bool = True):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + TOKEN} if authenticated else {}
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        value = json.loads(response.read())
        conn.close()
        return response.status, value

    def test_authenticated_fixed_get_projects_only_redacted_values(self) -> None:
        status, result = self.get(f"/v1/sites/{SITE_REF}/wifi/optimization")
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], {
            "mode": 1, "timeRangeEnable": True, "resource": 2,
            "timeRangeAction": 0,
        })
        self.assertTrue(result["partial"])
        encoded = json.dumps(result)
        for private in ("private-range-id", "privateExtension", "private-controller-value",
                        "known-site-id", "controller.example"):
            self.assertNotIn(private, encoded)
        self.assertEqual(self.upstream, [(
            "GET", "/openapi/v1/ctrl/sites/known-site-id/rrm/config",
            "synthetic-access-token")])
        self.assertTrue(all(method == "GET" for method, _path, _token in self.upstream))

    def test_auth_and_unknown_site_fail_before_controller_request(self) -> None:
        status, result = self.get(f"/v1/sites/{SITE_REF}/wifi/optimization", authenticated=False)
        self.assertEqual(status, 401)
        self.assertEqual(result["error"], "unauthorized")
        self.assertEqual(self.upstream, [])

        status, result = self.get(f"/v1/sites/{'b' * 24}/wifi/optimization")
        self.assertNotEqual(status, 200)
        self.assertEqual(self.upstream, [])
        self.assertNotIn("known-site-id", json.dumps(result))

    def test_missing_unknown_and_malformed_fields_are_reported_without_echo(self) -> None:
        self.payload = {
            "timeRangeEnable": "true", "resource": 99,
            "timeRangeAction": -1, "privateIdentifierField": "must-not-appear",
        }
        status, result = self.get(f"/v1/sites/{SITE_REF}/wifi/optimization")
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], {})
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_field_count"], 5)
        encoded = json.dumps(result)
        for private in ("privateIdentifierField", "must-not-appear", "timeRangeId"):
            self.assertNotIn(private, encoded)
        self.assertEqual(self.upstream[-1][0], "GET")


if __name__ == "__main__":
    unittest.main()
