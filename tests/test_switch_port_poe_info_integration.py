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
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


TOKEN = "switch-poe-info-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
SWITCH_REF = "c" * 24
OTHER_SWITCH_REF = "d" * 24
PRIVATE_SITE_ID = "private-site-id"
SWITCH_MAC = "AA-BB-CC-DD-EE-FF"
OTHER_SWITCH_MAC = "11:22:33:44:55:66"
PRIVATE_MARKERS = (
    "private-switch-name", "private-port-name", "private-site-name",
    "private-label-name", "private-stack-id", "private-stack-name",
    "private-pd-class",
)


def row(switch_mac: str = SWITCH_MAC, port: int = 4, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "switchMac": switch_mac,
        "port": port,
        "supportPoe": True,
        "poeDisplayType": 4,
        "poe": 1,
        "poeStatus": 0.9,
        "pdClass": PRIVATE_MARKERS[6],
        "power": 13.4,
        "voltage": 48.0,
        "current": 0.28,
        "switchName": PRIVATE_MARKERS[0],
        "portName": PRIVATE_MARKERS[1],
        "site": PRIVATE_MARKERS[2],
        "tagName": PRIVATE_MARKERS[3],
        "stackId": PRIVATE_MARKERS[4],
        "stackName": PRIVATE_MARKERS[5],
    }
    value.update(overrides)
    return value


class SwitchPortPoeInfoIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64, page_size=2, max_pages=3))
        self.client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        self.client._switch_macs_by_site_ref[SITE_REF] = {
            SWITCH_REF: SWITCH_MAC, OTHER_SWITCH_REF: OTHER_SWITCH_MAC,
        }
        self.client._switch_macs_by_site_ref[OTHER_SITE_REF] = {OTHER_SWITCH_REF: OTHER_SWITCH_MAC}
        self.rows: list[object] = [row(SWITCH_MAC, 4), row(OTHER_SWITCH_MAC, 7), row(SWITCH_MAC, 8)]
        self.upstream_calls: list[tuple[str, str, bytes | None]] = []
        self.fail_upstream = False

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.upstream_calls.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "synthetic-upstream-token")
            parsed = urlsplit(path)
            self.assertEqual(parsed.path,
                f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/switches/ports/poe-info")
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"page", "pageSize"})
            page = int(query["page"][0])
            page_size = int(query["pageSize"][0])
            self.assertEqual(page_size, self.client.config.page_size)
            start = (page - 1) * page_size
            page_rows = self.rows[start:start + page_size]
            if self.fail_upstream:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": {
                "totalRows": len(self.rows), "currentPage": page,
                "currentSize": len(page_rows), "data": json.loads(json.dumps(page_rows)),
            }}

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

    @staticmethod
    def public_path(site_ref: str = SITE_REF, switch_ref: str = SWITCH_REF) -> str:
        return f"/v1/sites/{site_ref}/switches/{switch_ref}/ports/poe-info"

    @staticmethod
    def upstream_path(controller_id: str = "ctrl") -> str:
        return f"/openapi/v1/{controller_id}/sites/{PRIVATE_SITE_ID}/switches/ports/poe-info"

    def request(self, method: str, path: str, *, token: str | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token is not None else {}
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

    def test_auth_binding_pagination_mac_filter_and_redaction(self) -> None:
        route = "GET /v1/sites/{site_ref}/switches/{switch_ref}/ports/poe-info"
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == route)
        self.assertEqual(operation["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"], [])

        status, denied = self.request("GET", self.public_path())
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "unauthorized")
        self.assertEqual(self.upstream_calls, [])

        status, value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["resource"], "switch_port_poe_info")
        self.assertEqual(value["switch_ref"], SWITCH_REF)
        self.assertEqual([item["port"] for item in value["data"]["items"]], [4, 8])
        self.assertEqual(value["data"]["items"][0], {
            "port": 4, "supportPoe": True, "poeDisplayType": 4, "poe": 1,
            "poeStatus": 0.9, "power": 13.4, "voltage": 48.0, "current": 0.28,
        })
        self.assertFalse(value["partial"])
        self.assertEqual(value["skipped_other_switch_count"], 1)
        self.assertEqual([parse_qs(urlsplit(call[1]).query)["page"][0]
                          for call in self.upstream_calls], ["1", "2"])
        self.assertTrue(all(call[0] == "GET" and call[2] is None
                            for call in self.upstream_calls))
        rendered = json.dumps(value)
        for private in (*PRIVATE_MARKERS, SWITCH_MAC, OTHER_SWITCH_MAC, PRIVATE_SITE_ID):
            self.assertNotIn(private, rendered)
            self.assertNotIn(private, self.logs.getvalue())

        before = len(self.upstream_calls)
        for site_ref, switch_ref in (("e" * 24, SWITCH_REF),
                                     (OTHER_SITE_REF, SWITCH_REF),
                                     (SITE_REF, "f" * 24)):
            status, error = self.request("GET", self.public_path(site_ref, switch_ref), token=TOKEN)
            self.assertNotEqual(status, 200)
            self.assertEqual(len(self.upstream_calls), before)
            self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))
            self.assertNotIn(SWITCH_MAC, json.dumps(error))

    def test_ambiguous_normalized_switch_mac_fails_before_controller_read(self) -> None:
        self.client._switch_macs_by_site_ref[SITE_REF][OTHER_SWITCH_REF] = "aa:bb:cc:dd:ee:ff"
        before = len(self.upstream_calls)
        status, error = self.request("GET", self.public_path(), token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(error["error"], "switch_ref_ambiguous")
        self.assertEqual(len(self.upstream_calls), before)
        self.assertNotIn(SWITCH_MAC, json.dumps(error))

    def test_missing_invalid_and_unknown_rows_mark_partial_and_redact(self) -> None:
        self.rows = [row(SWITCH_MAC, 4), row(port=5, switchMac=None),
                     row("not-a-mac", 6), row(SWITCH_MAC, 8, power=float("nan")),
                     row(SWITCH_MAC, 9, unknownPrivate="private-unrecognized-value")]
        status, value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        rendered = json.dumps(value)
        for private in (*PRIVATE_MARKERS, "not-a-mac", "switchMac", "unknownPrivate",
                        "private-unrecognized-value"):
            self.assertNotIn(private, rendered)
            self.assertNotIn(private, self.logs.getvalue())
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == "GET /v1/sites/{site_ref}/switches/{switch_ref}/ports/poe-info")
        self.assertEqual(operation["runtime_evidence"][-1]["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"][-1]["observation"], "response_partial")

    def test_max_pages_never_returns_silent_truncation(self) -> None:
        self.rows = [row(SWITCH_MAC, port) for port in range(1, 6)]
        self.client.config = OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64, page_size=2, max_pages=2)
        before = len(self.upstream_calls)
        status, error = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_page_limit_reached")
        self.assertEqual(len(self.upstream_calls) - before, 2)
        self.assertNotIn("items", error)

    def test_upstream_error_and_fixed_get_controller_query_allowlist(self) -> None:
        self.fail_upstream = True
        status, error = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_rejected")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64, page_size=2, max_pages=3))
        valid = self.upstream_path() + "?page=1&pageSize=2"
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", valid, token="token")
            rejected = (
                ("POST", valid), ("PUT", valid), ("PATCH", valid), ("DELETE", valid),
                ("GET", valid + "&debug=1"),
                ("GET", self.upstream_path("foreign-controller") + "?page=1&pageSize=2"),
                ("GET", valid.replace("/ports/poe-info", "/ports/other")),
                ("GET", valid.replace("pageSize=2", "pageSize=999")),
                ("GET", valid.replace("page=1", "page=4")),
            )
            for method, path in rejected:
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, token="token")

        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _ = self.request(method, self.public_path(), token=TOKEN)
            self.assertNotEqual(status, 200)
        for suffix in ("?debug=1", "?page=1", "?pageSize=2"):
            status, _ = self.request("GET", self.public_path() + suffix, token=TOKEN)
            self.assertNotEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
