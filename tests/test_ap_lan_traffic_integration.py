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


TOKEN = "ap-lan-traffic-integration-token-0123456789abcdef"
PRIVATE_SITE_ID = "private-site-id"
OTHER_PRIVATE_SITE_ID = "other-private-site-id"
AP_MAC = "AA-BB-CC-DD-EE-FF"
OTHER_AP_MAC = "11:22:33:44:55:66"
PRIVATE_NAME = "private-ap-name"
PRIVATE_IP = "192.0.2.220"
PRIVATE_TRAFFIC_NOTE = "private-traffic-note"


def full_lan_traffic(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "rxPkts": 101, "txPkts": 202, "rx": 3030, "tx": 4040,
        "rxDropPkts": 5, "txDropPkts": 6, "rxErrPkts": 7, "txErrPkts": 8,
    }
    fields.update(overrides)
    return fields


class ApLanTrafficIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.site_rows: list[object] = [
            {"siteId": PRIVATE_SITE_ID, "name": PRIVATE_NAME},
            {"siteId": OTHER_PRIVATE_SITE_ID, "name": "other-private-site"},
        ]
        self.device_rows = {
            PRIVATE_SITE_ID: [{"mac": AP_MAC, "deviceType": "AP", "name": PRIVATE_NAME,
                               "ip": PRIVATE_IP, "deviceModel": "private-model"}],
            OTHER_PRIVATE_SITE_ID: [{"mac": OTHER_AP_MAC, "deviceType": "AP",
                                     "name": "other-private-ap"}],
        }
        self.result: object = {"lanTraffic": full_lan_traffic()}
        self.transport_calls: list[tuple[str, str, bytes | None]] = []
        self.fail_upstream = False

        def page(rows: list[object], query: dict[str, list[str]]) -> dict[str, object]:
            page_number = int(query["page"][0])
            page_size = int(query["pageSize"][0])
            start = (page_number - 1) * page_size
            data = rows[start:start + page_size]
            return {"result": {"data": data, "totalRows": len(rows),
                               "currentPage": page_number, "currentSize": len(data)}}

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "synthetic-upstream-token")
            parsed = urlsplit(path)
            if parsed.path == "/openapi/v1/ctrl/sites":
                query = parse_qs(parsed.query, strict_parsing=True)
                self.assertEqual(set(query), {"page", "pageSize"})
                return page(self.site_rows, query)
            for site_id, rows in self.device_rows.items():
                if parsed.path == f"/openapi/v1/ctrl/sites/{site_id}/devices":
                    query = parse_qs(parsed.query, strict_parsing=True)
                    self.assertEqual(set(query), {"page", "pageSize"})
                    return page(rows, query)
            self.assertEqual(parsed.path, self._upstream_path())
            self.assertEqual(parsed.query, "")
            if self.fail_upstream:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": json.loads(json.dumps(self.result))}

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
    def _upstream_path(controller_id: str = "ctrl", site_id: str = PRIVATE_SITE_ID,
                       ap_mac: str = AP_MAC) -> str:
        return (f"/openapi/v1/{controller_id}/sites/{site_id}/aps/"
                f"{ap_mac}/lan-traffic-info")

    @staticmethod
    def _public_path(site_ref: str, device_ref: str) -> str:
        return f"/v1/sites/{site_ref}/aps/{device_ref}/lan-traffic"

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

    def inventories(self) -> tuple[str, str, str]:
        status, sites = self.request("GET", "/v1/sites", token=TOKEN)
        self.assertEqual(status, 200, sites)
        refs = [row["site_ref"] for row in sites["items"]]
        status, ap_list = self.request("GET", f"/v1/sites/{refs[0]}/devices", token=TOKEN)
        self.assertEqual(status, 200, ap_list)
        self.assertEqual(ap_list["resource"], "devices")
        self.assertEqual(ap_list["count"], 1)
        device_ref = ap_list["items"][0]["device_ref"]
        # Resolve another AP in its own site so the cross-site check is not
        # merely a consequence of an unknown device reference.
        status, other_list = self.request("GET", f"/v1/sites/{refs[1]}/devices", token=TOKEN)
        self.assertEqual(status, 200, other_list)
        self.assertEqual(other_list["count"], 1)
        return refs[0], refs[1], device_ref

    def test_auth_inventory_bound_projection_units_and_redaction(self) -> None:
        site_ref, _other_site_ref, device_ref = self.inventories()
        operation_route = "GET /v1/sites/{site_ref}/aps/{device_ref}/lan-traffic"
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == operation_route)
        self.assertEqual(operation["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"], [])

        before = len(self.transport_calls)
        status, denied = self.request("GET", self._public_path(site_ref, device_ref))
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "unauthorized")
        self.assertEqual(len(self.transport_calls), before)

        status, value = self.request("GET", self._public_path(site_ref, device_ref), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["resource"], "ap_lan_traffic")
        self.assertEqual(value["site_ref"], site_ref)
        self.assertEqual(value["device_ref"], device_ref)
        self.assertEqual(value["data"], full_lan_traffic())
        self.assertFalse(value["partial"])
        self.assertEqual(self.transport_calls[-1], ("GET", self._upstream_path(), None))
        rendered = json.dumps(value)
        for private in (PRIVATE_SITE_ID, OTHER_PRIVATE_SITE_ID, AP_MAC, OTHER_AP_MAC,
                        PRIVATE_NAME, PRIVATE_IP, "private-model", PRIVATE_TRAFFIC_NOTE):
            self.assertNotIn(private, rendered)
            self.assertNotIn(private, self.logs.getvalue())
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == operation_route)
        evidence = operation["runtime_evidence"][-1]
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["response_shape_state"], "response_shape_supported")
        self.assertFalse(evidence["controller_response_observed"])

    def test_missing_invalid_unknown_values_are_partial_and_redacted(self) -> None:
        site_ref, _other_site_ref, device_ref = self.inventories()
        operation_route = "GET /v1/sites/{site_ref}/aps/{device_ref}/lan-traffic"
        fixtures = (
            {"lanTraffic": {k: v for k, v in full_lan_traffic().items() if k != "rxPkts"}},
            {"lanTraffic": full_lan_traffic(rx=True)},
            {"lanTraffic": full_lan_traffic(txDropPkts=-1)},
            {"lanTraffic": {**full_lan_traffic(), "privateTraffic": PRIVATE_TRAFFIC_NOTE}},
        )
        for self.result in fixtures:
            with self.subTest(result=self.result):
                status, value = self.request("GET", self._public_path(site_ref, device_ref), token=TOKEN)
                self.assertEqual(status, 200, value)
                self.assertTrue(value["partial"])
                self.assertNotIn("privateTraffic", json.dumps(value))
                self.assertNotIn(PRIVATE_TRAFFIC_NOTE, json.dumps(value))
                self.assertNotIn(PRIVATE_TRAFFIC_NOTE, self.logs.getvalue())
                operation = next(item for item in self.client.capabilities()["items"]
                                 if item["route"] == operation_route)
                self.assertEqual(operation["runtime_evidence"][-1]["support_state"], "unknown")

    def test_unknown_sibling_wrapper_field_marks_partial_without_leaking(self) -> None:
        site_ref, _other_site_ref, device_ref = self.inventories()
        self.result = {"lanTraffic": full_lan_traffic(),
                       "privateWrapperField": PRIVATE_TRAFFIC_NOTE}
        status, value = self.request("GET", self._public_path(site_ref, device_ref), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        self.assertEqual(value["data"], full_lan_traffic())
        for private in ("privateWrapperField", PRIVATE_TRAFFIC_NOTE, PRIVATE_SITE_ID, AP_MAC):
            self.assertNotIn(private, json.dumps(value))
            self.assertNotIn(private, self.logs.getvalue())

    def test_unknown_and_cross_site_device_refs_are_rejected_before_upstream(self) -> None:
        site_ref, other_site_ref, device_ref = self.inventories()
        before = len(self.transport_calls)
        for route in (
                self._public_path("f" * 24, device_ref),
                self._public_path(other_site_ref, device_ref),
                self._public_path(site_ref, "e" * 24)):
            status, error = self.request("GET", route, token=TOKEN)
            self.assertNotEqual(status, 200)
            self.assertEqual(len(self.transport_calls), before)
            self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))
            self.assertNotIn(AP_MAC, json.dumps(error))

    def test_public_route_is_get_only_and_rejects_query_and_invalid_path(self) -> None:
        site_ref, _other_site_ref, device_ref = self.inventories()
        before = len(self.transport_calls)
        route = self._public_path(site_ref, device_ref)
        for method, path in (("GET", route + "?raw=true"),
                              ("POST", route), ("PUT", route), ("PATCH", route),
                              ("DELETE", route),
                              ("GET", route.replace("/lan-traffic", "/other"))):
            status, _ = self.request(method, path, token=TOKEN)
            self.assertNotEqual(status, 200)
            self.assertEqual(len(self.transport_calls), before)

    def test_upstream_guard_allows_only_exact_controller_route_and_get(self) -> None:
        guard_client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        valid = self._upstream_path()
        with patch.object(guard_client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                guard_client._request_json("GET", valid, token="token")
        for method, path in (
                ("POST", valid), ("PUT", valid), ("PATCH", valid), ("DELETE", valid),
                ("GET", valid + "?raw=true"),
                ("GET", self._upstream_path("foreign-controller")),
                ("GET", valid.replace("lan-traffic-info", "other"))):
            with self.subTest(method=method, path=path):
                with self.assertRaises(OpenApiError) as caught:
                    guard_client._request_json(method, path, token="token")
                self.assertEqual(caught.exception.code, "openapi_path_rejected")


if __name__ == "__main__":
    unittest.main()
