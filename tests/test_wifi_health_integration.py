from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF = "a" * 24
UNKNOWN_SITE_REF = "b" * 24
PRIVATE_SITE_ID = "private-site-id"
PRIVATE_NAME = "private controller name"
PRIVATE_ADDRESS = "192.0.2.25"


class WifiHealthIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.token = "wifi-health-fixture-token-0123456789abcdef"
        self.token_file = os.path.join(self.tempdir.name, "token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(self.token)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id-file", "secret-file",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        self.upstream: list[tuple[str, str, bytes | None]] = []
        self.fail_upstream = False

        def request(method: str, path: str, body: bytes | None = None,
                    token: str | None = None):
            self.upstream.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "upstream-fixture-token")
            parsed = urlsplit(path)
            self.assertEqual(parsed.path,
                "/openapi/v1/ctrl/sites/private-site-id/wifi/health/timeline")
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"start", "end"})
            start_ms, end_ms = int(query["start"][0]), int(query["end"][0])
            self.assertEqual(end_ms - start_ms, 86_400_000)
            if self.fail_upstream:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": {"scores": [
                {"time": start_ms, "score": 75, "name": PRIVATE_NAME,
                 "ip": PRIVATE_ADDRESS, "id": "raw-score-id"},
                {"time": end_ms, "score": 81},
            ], "private": PRIVATE_NAME}}

        self.request_patch = patch.object(self.client, "_request_json", side_effect=request)
        self.request_patch.start()
        self.access_patch = patch.object(self.client, "_access_token",
                                         return_value="upstream-fixture-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_file})
        self.env_patch.start()
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
        self.env_patch.stop()
        self.access_patch.stop()
        self.request_patch.stop()
        self.tempdir.cleanup()

    def get(self, path: str, token: str | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token is not None else {}
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        status = response.status
        connection.close()
        return status, json.loads(raw)

    def test_protected_http_projection_and_fixed_controller_get(self) -> None:
        route = f"/v1/sites/{SITE_REF}/wifi/health/timeline"
        status, error = self.get(route)
        self.assertEqual(status, 401)
        self.assertEqual(error["error"], "unauthorized")
        self.assertEqual(self.upstream, [])

        status, result = self.get(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["query_time_unit"], "milliseconds_documented_not_live_verified")
        self.assertEqual(len(self.upstream), 1)
        self.assertEqual(self.upstream[0][0], "GET")
        self.assertIsNone(self.upstream[0][2])
        scores = result["data"]["scores"]
        self.assertEqual(len(scores), 2)
        self.assertEqual({row["score"] for row in scores}, {75, 81})
        self.assertEqual(result["data"]["partial"], True)
        self.assertEqual(result["data"]["counts"]["unknown_fields"], 4)
        rendered = json.dumps(result)
        for private in (PRIVATE_SITE_ID, PRIVATE_NAME, PRIVATE_ADDRESS, "raw-score-id"):
            self.assertNotIn(private, rendered)

    def test_unknown_site_ref_fails_before_upstream_request(self) -> None:
        status, body = self.get(f"/v1/sites/{UNKNOWN_SITE_REF}/wifi/health/timeline", self.token)
        self.assertEqual(status, 502)
        self.assertEqual(body["error"], "site_ref_unknown")
        self.assertEqual(self.upstream, [])

    def test_upstream_rejection_is_reported_without_raw_message(self) -> None:
        self.fail_upstream = True
        status, body = self.get(f"/v1/sites/{SITE_REF}/wifi/health/timeline", self.token)
        self.assertEqual(status, 502)
        self.assertEqual(body["error"], "openapi_rejected")
        self.assertNotIn("private", json.dumps(body))

    def test_fixed_route_rejects_arbitrary_paths_methods_and_query_keys(self) -> None:
        invalid = (
            ("POST", "/openapi/v1/ctrl/sites/private-site-id/wifi/health/timeline?start=1&end=86400001"),
            ("GET", "/openapi/v1/ctrl/sites/private-site-id/wifi/health/other?start=1&end=2"),
            ("GET", "/openapi/v1/other/sites/private-site-id/wifi/health/timeline?start=1&end=2"),
            ("GET", "/openapi/v1/ctrl/sites/private-site-id/wifi/health/timeline?start=1&end=2&extra=3"),
            ("GET", "/openapi/v1/ctrl/sites/private-site-id/wifi/health/timeline?start=2&end=1"),
        )
        with patch.object(self.client, "_connection",
                          side_effect=AssertionError("network must not start")):
            for method, path in invalid:
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    OmadaOpenApiClient._request_json(self.client, method, path)


if __name__ == "__main__":
    unittest.main()
