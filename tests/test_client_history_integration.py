from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import threading
import unittest
from dataclasses import replace
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


TOKEN = "client-history-caller-token-0123456789abcdef"
OTHER_TOKEN = "wrong-caller-token-0123456789abcdef"
PRIVATE_SITE_ID = "private-site-id"
OTHER_PRIVATE_SITE_ID = "other-private-site-id"
PRIVATE_CLIENT_MAC = "AA-BB-CC-DD-EE-FF"
OTHER_CLIENT_MAC = "11:22:33:44:55:66"
PRIVATE_NAME = "private-client-name"
PRIVATE_IP = "192.0.2.91"
PRIVATE_IPV6 = "2001:db8::91"
PRIVATE_SSID = "private-ssid"
PRIVATE_REASON = "private-disconnect-reason"
PRIVATE_AUTH = "private-auth-info"


class ClientHistoryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64, page_size=2, max_pages=2))
        self.site_rows = [{"siteId": PRIVATE_SITE_ID, "name": PRIVATE_NAME},
                          {"siteId": OTHER_PRIVATE_SITE_ID, "name": "other-site-name"}]
        self.calls: list[tuple[str, str, bytes | None]] = []
        self.history_rows: list[object] = []
        self.fail_page: int | None = None

        def page(rows: list[object], query: dict[str, list[str]]) -> dict[str, object]:
            current = int(query["page"][0])
            size = int(query["pageSize"][0])
            if self.fail_page == current:
                return {"result": {"data": [], "totalRows": len(rows),
                                   "currentPage": current, "currentSize": 0}}
            start = (current - 1) * size
            data = rows[start:start + size]
            return {"result": {"data": data, "totalRows": len(rows),
                               "currentPage": current, "currentSize": len(data)}}

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.calls.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "synthetic-upstream-token")
            parsed = urlsplit(path)
            query = parse_qs(parsed.query, strict_parsing=True)
            if parsed.path == "/openapi/v1/ctrl/sites":
                self.assertEqual(set(query), {"page", "pageSize"})
                return page(self.site_rows, query)
            if parsed.path == f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/clients":
                self.assertEqual(set(query), {"page", "pageSize"})
                return page([{"mac": PRIVATE_CLIENT_MAC, "name": PRIVATE_NAME,
                              "ip": PRIVATE_IP, "wireless": True}], query)
            if parsed.path == f"/openapi/v1/ctrl/sites/{OTHER_PRIVATE_SITE_ID}/clients":
                self.assertEqual(set(query), {"page", "pageSize"})
                return page([{"mac": OTHER_CLIENT_MAC, "wireless": True}], query)
            self.assertEqual(parsed.path,
                f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/clients/{PRIVATE_CLIENT_MAC}/client-history")
            self.assertEqual(set(query), {"page", "pageSize"})
            page_no = int(query["page"][0])
            return page(self.history_rows, query)

        self.transport_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.transport_patch.start()
        self.access_patch = patch.object(
            self.client, "_access_token", return_value="synthetic-upstream-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_file})
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.logs = io.StringIO()
        self.print_patch = patch.object(
            builtins, "print", lambda *args, **_kwargs: self.logs.write(
                " ".join(map(str, args)) + "\n"))
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
        self.transport_patch.stop()
        self.temp.cleanup()

    def request(self, method: str, path: str, *, token: str | None = TOKEN):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token else {}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        status = response.status
        connection.close()
        return status, value

    def inventory(self) -> tuple[str, str, str]:
        status, sites = self.request("GET", "/v1/sites")
        self.assertEqual(status, 200, sites)
        refs = [item["site_ref"] for item in sites["items"]]
        self.assertEqual(sites["count"], 2)
        status, clients = self.request("GET", f"/v1/sites/{refs[0]}/clients")
        self.assertEqual(status, 200, clients)
        self.assertEqual(clients["resource"], "clients")
        self.assertEqual(clients["count"], 1)
        return refs[0], refs[1], clients["items"][0]["client_ref"]

    @staticmethod
    def row(mac: object = PRIVATE_CLIENT_MAC, **extra: object) -> dict[str, object]:
        return {
            "id": "private-history-row-id", "mac": mac,
            "download": 1234, "upload": 5678, "duration": 900,
            "lastSeen": 1767355000, "name": PRIVATE_NAME, "ssid": PRIVATE_SSID,
            "port": 3, "vid": 42, "reason": PRIVATE_REASON,
            "reasonType": 4, "guest": False, "deviceName": PRIVATE_NAME,
            "associationTime": 12, "associated": 1767354000,
            "ip": PRIVATE_IP, "ipv6List": [PRIVATE_IPV6],
            "authInfo": [{"authType": 1, "info": PRIVATE_AUTH}], **extra,
        }

    def history_path(self, site_ref: str, client_ref: str) -> str:
        return f"/v1/sites/{site_ref}/clients/{client_ref}/history"

    def test_auth_fresh_reference_pagination_privacy_and_capability(self) -> None:
        status, denied = self.request("GET", self.history_path("a" * 24, "c" * 24), token=None)
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "unauthorized")
        self.assertEqual(self.calls, [])

        site_ref, _other_ref, client_ref = self.inventory()
        self.history_rows = [self.row(), self.row(download=2222), self.row()]
        operation_route = "GET /v1/sites/{site_ref}/clients/{client_ref}/history"
        initial = next(item for item in self.client.capabilities()["items"]
                       if item["route"] == operation_route)
        self.assertEqual(initial["support_state"], "unknown")
        self.assertEqual(initial["runtime_evidence"], [])

        status, value = self.request("GET", self.history_path(site_ref, client_ref))
        self.assertEqual(status, 200, value)
        self.assertEqual(value["resource"], "client_history")
        self.assertEqual(value["site_ref"], site_ref)
        self.assertEqual(value["client_ref"], client_ref)
        self.assertFalse(value["partial"])
        self.assertEqual(value["data"]["count"], 3)
        self.assertEqual(len(value["data"]["rows"]), 3)
        route_calls = [path for method, path, _body in self.calls
                       if "/client-history?" in path]
        self.assertEqual(len(route_calls), 2)
        for page_no, path in enumerate(route_calls, 1):
            parsed = urlsplit(path)
            self.assertEqual(parsed.path,
                f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/clients/{PRIVATE_CLIENT_MAC}/client-history")
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"page", "pageSize"})
            self.assertEqual(query["page"], [str(page_no)])
            self.assertEqual(query["pageSize"], ["2"])
        self.assertTrue(all(method == "GET" and body is None for method, _path, body in self.calls))
        rendered = json.dumps(value)
        for private in (PRIVATE_SITE_ID, OTHER_PRIVATE_SITE_ID, PRIVATE_CLIENT_MAC,
                        OTHER_CLIENT_MAC, PRIVATE_NAME, PRIVATE_IP, PRIVATE_IPV6,
                        PRIVATE_SSID, PRIVATE_REASON, PRIVATE_AUTH, "private-history-row-id"):
            self.assertNotIn(private, rendered)
            self.assertNotIn(private, self.logs.getvalue())
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["route"] == operation_route)["runtime_evidence"][-1]
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["response_shape_state"], "response_shape_supported")
        self.assertFalse(evidence["controller_response_observed"])

    def test_rows_with_missing_invalid_or_foreign_macs_are_omitted_and_partial(self) -> None:
        site_ref, _other_ref, client_ref = self.inventory()
        self.history_rows = [self.row(), self.row(mac=None), self.row(mac="bad-private-mac"),
                             self.row(mac=OTHER_CLIENT_MAC)]
        status, value = self.request("GET", self.history_path(site_ref, client_ref))
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        self.assertEqual(value["data"]["count"], 1)
        self.assertEqual(len(value["data"]["rows"]), 1)
        for private in (OTHER_CLIENT_MAC, "bad-private-mac", PRIVATE_CLIENT_MAC,
                        PRIVATE_NAME, PRIVATE_REASON, PRIVATE_AUTH):
            self.assertNotIn(private, json.dumps(value))
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == "GET /v1/sites/{site_ref}/clients/{client_ref}/history")
        self.assertEqual(operation["runtime_evidence"][-1]["support_state"], "unknown")

    def test_site_binding_stale_reference_and_rotation(self) -> None:
        site_ref, other_ref, client_ref = self.inventory()
        status, other_clients = self.request("GET", f"/v1/sites/{other_ref}/clients")
        self.assertEqual(status, 200, other_clients)
        before = len([path for _method, path, _body in self.calls if "/client-history?" in path])
        status, wrong_site = self.request("GET", self.history_path(other_ref, client_ref))
        self.assertIn(status, (400, 404, 502))
        self.assertEqual(len([path for _method, path, _body in self.calls
                              if "/client-history?" in path]), before)

        status, fresh_clients = self.request("GET", f"/v1/sites/{site_ref}/clients")
        self.assertEqual(status, 200, fresh_clients)
        self.assertNotEqual(client_ref, fresh_clients["items"][0]["client_ref"])
        before = len([path for _method, path, _body in self.calls if "/client-history?" in path])
        status, stale = self.request("GET", self.history_path(site_ref, client_ref))
        self.assertIn(status, (400, 404, 502))
        self.assertEqual(len([path for _method, path, _body in self.calls
                              if "/client-history?" in path]), before)
        self.assertNotIn(PRIVATE_CLIENT_MAC, json.dumps(stale))

    def test_page_limit_fails_closed_without_truncated_result(self) -> None:
        site_ref, _other_ref, client_ref = self.inventory()
        self.history_rows = [self.row(), self.row(), self.row()]
        self.client.config = replace(self.client.config, max_pages=1)
        status, value = self.request("GET", self.history_path(site_ref, client_ref))
        self.assertEqual(status, 502)
        self.assertEqual(value.get("error"), "openapi_page_limit_reached")
        self.assertNotIn("rows", value.get("data", {}))
        self.assertEqual(len([path for _method, path, _body in self.calls
                              if "/client-history?" in path]), 1)
        self.assertNotIn(PRIVATE_NAME, json.dumps(value))

    def test_invalid_reference_query_extra_method_and_other_controller_are_rejected(self) -> None:
        site_ref, _other_ref, client_ref = self.inventory()
        path = self.history_path(site_ref, client_ref)
        before = len(self.calls)
        status, _ = self.request("GET", path + "?page=99")
        self.assertIn(status, (400, 404))
        status, _ = self.request("POST", path)
        self.assertNotEqual(status, 200)
        status, _ = self.request("GET", self.history_path("f" * 24, client_ref))
        self.assertNotEqual(status, 200)
        self.assertEqual(len([call for call in self.calls[before:]
                              if "/client-history?" in call[1]]), 0)

        guard_client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64, page_size=2, max_pages=2))
        valid_base = (f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/clients/"
                      f"{PRIVATE_CLIENT_MAC}/client-history?page=1&pageSize=2")
        for method, rejected_path in (
                ("GET", valid_base.replace("/openapi/v1/ctrl/", "/openapi/v1/other/")),
                ("GET", valid_base + "&searchKey=private"),
                ("POST", valid_base)):
            with self.subTest(method=method, rejected_path=rejected_path):
                with self.assertRaises(OpenApiError) as caught:
                    guard_client._request_json(method, rejected_path)
                self.assertEqual(caught.exception.code, "openapi_path_rejected")


if __name__ == "__main__":
    unittest.main()
