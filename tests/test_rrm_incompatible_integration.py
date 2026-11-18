from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


TOKEN = "rrm-incompatible-caller-token-0123456789abcdef"
SITE_REF = "a" * 24
AP_REF = "b" * 24
SECOND_AP_REF = "c" * 24


class FakeController:
    def __init__(self):
        self.calls: list[tuple[str, str, str | None]] = []
        self.pages = {
            1: {
                "totalRows": 3, "currentPage": 1, "currentSize": 2,
                "data": [
                    {"name": "private-ap-one", "mac": "AA-BB-CC-DD-EE-01",
                     "statusCategory": 1, "status": 17, "version": "7.2.1",
                     "type": "AP", "model": "private-model", "modelVersion": "v3",
                     "showModel": "private-display-model"},
                    {"name": "private-unknown", "mac": "AA-BB-CC-DD-EE-99",
                     "statusCategory": 0, "status": 3, "model": "unknown-model"},
                ],
            },
            2: {
                "totalRows": 3, "currentPage": 2, "currentSize": 1,
                "data": [
                    {"name": "private-ap-two", "mac": "aa:bb:cc:dd:ee:02",
                     "statusCategory": 8, "status": True,
                     "privateExtension": "secret-extension"},
                ],
            },
        }

    def request(self, method: str, path: str, *, token: str | None = None, **_kwargs):
        self.calls.append((method, path, token))
        query = parse_qs(urlsplit(path).query)
        page = int(query["page"][0])
        return {"errorCode": 0, "result": self.pages[page]}


class RrmIncompatibleApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = Path(self.temp.name) / "caller-token"
        self.token_file.write_text(TOKEN, encoding="ascii")
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64, page_size=2, max_pages=3))
        self.client._site_ids_by_ref[SITE_REF] = "known-site-id"
        self.client._device_macs_by_site_ref[SITE_REF] = {
            AP_REF: "AA-BB-CC-DD-EE-01",
            SECOND_AP_REF: "AA-BB-CC-DD-EE-02",
        }
        self.controller = FakeController()
        self.request_patch = patch.object(self.client, "_request_json",
                                          side_effect=self.controller.request)
        self.request_patch.start()
        self.access_patch = patch.object(self.client, "_access_token",
                                         return_value="synthetic-controller-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": str(self.token_file)})
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
        self.temp.cleanup()

    def http(self, method: str, path: str, *, authenticated: bool = True):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + TOKEN} if authenticated else {}
        conn.request(method, path, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        status = response.status
        conn.close()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return status, body

    def test_pagination_inventory_mapping_and_redaction_over_authenticated_http(self) -> None:
        path = f"/v1/sites/{SITE_REF}/wifi/rrm-incompatible"
        status, body = self.http("GET", path, authenticated=False)
        self.assertEqual(status, 401)
        self.assertEqual(self.controller.calls, [])

        status, body = self.http("GET", path)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "rrm_incompatible_aps")
        self.assertEqual(body["site_ref"], SITE_REF)
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["unknown_entry_count"], 1)
        self.assertEqual(body["unknown_field_count"], 1)
        self.assertTrue(body["partial"])
        first, second = body["items"]
        self.assertEqual(first, {"device_ref": AP_REF, "status_category": 1,
                                 "status_code": 17, "partial": False})
        self.assertEqual(second, {"device_ref": SECOND_AP_REF, "status_category": None,
                                  "status_code": None, "partial": True})
        self.assertEqual(self.controller.calls, [
            ("GET", "/openapi/v1/ctrl/sites/known-site-id/rrm/incompatible?page=1&pageSize=2",
             "synthetic-controller-token"),
            ("GET", "/openapi/v1/ctrl/sites/known-site-id/rrm/incompatible?page=2&pageSize=2",
             "synthetic-controller-token"),
        ])
        encoded = json.dumps(body, sort_keys=True)
        for private in ("AA-BB-CC-DD-EE-01", "aa:bb:cc:dd:ee:02", "AA-BB-CC-DD-EE-99",
                        "private-ap-one", "private-unknown", "private-ap-two", "unknown-model",
                        "private-model", "v3", "private-display-model", "7.2.1",
                        "secret-extension", "known-site-id", "controller.example"):
            self.assertNotIn(private, encoded)

    def test_unknown_invalid_mac_and_missing_fields_are_partial_without_leaks(self) -> None:
        self.controller.pages = {1: {
            "totalRows": 3, "currentPage": 1, "currentSize": 2,
            "data": [
                {"mac": "not-a-mac", "name": "invalid-row-private"},
                {"mac": "AA-BB-CC-DD-EE-99", "name": "unknown-private"},
            ],
        }, 2: {
            "totalRows": 3, "currentPage": 2, "currentSize": 1,
            "data": [
                {"mac": "AA-BB-CC-DD-EE-01", "status": 4,
                 "name": "known-private", "model": "private-model"},
            ],
        }}
        body = self.client.read_rrm_incompatible(SITE_REF)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["unknown_entry_count"], 2)
        self.assertTrue(body["partial"])
        self.assertEqual(body["items"], [{"device_ref": AP_REF, "status_category": None,
                                           "status_code": 4, "partial": True}])
        for private in ("not-a-mac", "AA-BB-CC-DD-EE-99", "invalid-row-private",
                        "unknown-private", "known-private", "private-model"):
            self.assertNotIn(private, json.dumps(body))

    def test_only_fixed_get_route_and_controller_path_are_allowed(self) -> None:
        good = "/openapi/v1/ctrl/sites/known-site-id/rrm/incompatible?page=1&pageSize=2"
        with patch.object(self.client, "_connection",
                          side_effect=OpenApiError("synthetic_connection_boundary")):
            with self.assertRaisesRegex(OpenApiError, "synthetic_connection_boundary"):
                OmadaOpenApiClient._request_json(self.client, "GET", good, token="fake")
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                with self.subTest(method=method), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    OmadaOpenApiClient._request_json(self.client, method, good,
                                                     body=b"{}", token="fake")
            for foreign in (
                good.replace("/openapi/v1/ctrl/", "/openapi/v1/other/"),
                good + "&searchKey=secret",
                good + "&sorts.name=asc",
                good.replace("/rrm/incompatible", "/rrm/config"),
                good.replace("page=1", "page=0"),
                good.replace("page=1", "page=4"),  # max_pages is three
                good.replace("pageSize=2", "pageSize=1"),
            ):
                with self.subTest(foreign=foreign), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    OmadaOpenApiClient._request_json(self.client, "GET", foreign,
                                                     token="fake")

    def test_http_wrong_route_and_write_verb_never_reach_controller(self) -> None:
        path = f"/v1/sites/{SITE_REF}/wifi/rrm-incompatible"
        status, _body = self.http("GET", path + "?extra=1")
        self.assertEqual(status, 404)
        self.assertEqual(self.controller.calls, [])
        status, _body = self.http("POST", path)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.controller.calls, [])


if __name__ == "__main__":
    unittest.main()
