from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import StringIO
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE, SWITCH, OTHER = "a" * 24, "b" * 24, "c" * 24
SWITCH_MAC = "00-11-22-33-44-55"


class FakeLldpClient:
    def __init__(self) -> None:
        self.calls = []

    def read_switch_lldp_neighbors(self, site_ref: str, switch_ref: str):
        self.calls.append((site_ref, switch_ref))
        if site_ref != SITE:
            raise OpenApiError("site_ref_unknown")
        if switch_ref != SWITCH:
            raise OpenApiError("switch_ref_unknown")
        return {"status": "ok", "resource": "switch_lldp_neighbors",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "data": {"scope": "ports_with_returned_lldp_neighbors_only",
                         "ports": [{"port_id": 7, "neighbor_present": True,
                                    "neighbor_count": 1}],
                         "neighbor_entry_count": 1, "projected_neighbor_entry_count": 1,
                         "port_count": 1, "omitted_field_count": 4,
                         "omitted_neighbor_entry_count": 0, "partial": False}}


class SwitchLldpIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=2, max_pages=3))
        self.client._site_ids_by_ref[SITE] = "site_1"
        self.client._switch_macs_by_site_ref[SITE] = {SWITCH: SWITCH_MAC}

    def test_pagination_rejects_float_page_number(self) -> None:
        response = {"result": {"totalRows": 0, "currentPage": 1.0,
                               "currentSize": 0, "data": []}}
        with patch.object(self.client, "_access_token", return_value="fixture-token"), \
                patch.object(self.client, "_request_json", return_value=response):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_switch_lldp_neighbors(SITE, SWITCH)

    def test_inventory_bound_fixed_paged_get_projection_and_capability(self) -> None:
        private_mac = "AA:BB:CC:DD:EE:FF"
        private_name = "private neighbor system"
        calls = []
        pages = {
            1: {"result": {"totalRows": 3, "currentPage": 1, "currentSize": 2,
                            "data": [{"portId": 7, "systemName": private_name,
                                      "deviceId": "raw-device-id", "neighborPortId": private_mac},
                                     {"portId": 8, "standardPort": "Port 8", "ttl": 90}]}},
            2: {"result": {"totalRows": 3, "currentPage": 2, "currentSize": 1,
                            "data": [{"portId": 7, "capabilities": "bridge",
                                      "neighborPortId": private_mac}]}},
        }

        def request(method: str, path: str, *, token: str | None = None, **_kwargs):
            calls.append((method, path, token))
            self.assertEqual(method, "GET")
            self.assertEqual(token, "fixture-token")
            self.assertTrue(path.startswith(
                f"/openapi/v1/ctrl/sites/site_1/switches/{SWITCH_MAC}/lldp-neighbors?"))
            page = int(path.partition("?page=")[2].split("&", 1)[0])
            self.assertEqual(path.rsplit("&", 1)[1], "pageSize=2")
            return pages[page]

        with patch.object(self.client, "_access_token", return_value="fixture-token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_switch_lldp_neighbors(SITE, SWITCH)

        self.assertEqual([item[1] for item in calls], [
            f"/openapi/v1/ctrl/sites/site_1/switches/{SWITCH_MAC}/lldp-neighbors?page=1&pageSize=2",
            f"/openapi/v1/ctrl/sites/site_1/switches/{SWITCH_MAC}/lldp-neighbors?page=2&pageSize=2",
        ])
        self.assertEqual(result["data"]["ports"], [
            {"port_id": 7, "neighbor_present": True, "neighbor_count": 2},
            {"port_id": 8, "neighbor_present": True, "neighbor_count": 1},
        ])
        rendered = str(result)
        for forbidden in (private_mac, private_name, "raw-device-id", "Port 8", "bridge"):
            self.assertNotIn(forbidden, rendered)
        evidence = next(row for row in self.client.capabilities()["items"]
                        if row["operation"] == "switch_lldp_neighbors")["runtime_evidence"]
        self.assertEqual(evidence[0]["target_ref"], SITE + ":" + SWITCH)

    def test_unknown_or_cross_site_refs_fail_before_upstream_request(self) -> None:
        with patch.object(self.client, "_request_json",
                          side_effect=AssertionError("upstream must not be called")):
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_switch_lldp_neighbors(OTHER, SWITCH)
            with self.assertRaisesRegex(OpenApiError, "switch_ref_unknown"):
                self.client.read_switch_lldp_neighbors(SITE, OTHER)
            with self.assertRaisesRegex(OpenApiError, "switch_ref_invalid"):
                self.client.read_switch_lldp_neighbors(SITE, "not-a-ref")

    def test_fixed_get_allowlist_rejects_other_method_controller_or_path(self) -> None:
        valid = f"/openapi/v1/ctrl/sites/site_1/switches/{SWITCH_MAC}/lldp-neighbors?page=1&pageSize=2"
        with patch.object(self.client, "_connection",
                          side_effect=AssertionError("network must not start")):
            for method, path in (
                ("POST", valid),
                ("GET", valid.replace("/ctrl/", "/other/")),
                ("GET", valid.replace("/lldp-neighbors?", "/lldp-neighbors/extra?")),
                ("GET", valid.replace("&pageSize=2", "&pageSize=2&searchKey=private")),
            ):
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    self.client._request_json(method, path)

    def test_http_auth_dispatch_redaction_invalid_refs_and_get_only(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            token_path = os.path.join(tempdir, "caller-token")
            with open(token_path, "w", encoding="ascii") as stream:
                stream.write("test-caller-token-that-is-long-enough\n")
            fake = FakeLldpClient()
            server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            env = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_path})
            env.start()
            client_patch = patch.object(main, "_openapi_client", return_value=fake)
            client_patch.start()
            captured = StringIO()
            try:
                with redirect_stdout(captured):
                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    connection.request("GET", f"/v1/sites/{SITE}/switches/{SWITCH}/lldp-neighbors")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 401)
                    response.read()
                    connection.close()

                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    connection.request("GET", f"/v1/sites/{SITE}/switches/{SWITCH}/lldp-neighbors",
                                       headers={"Authorization": "Bearer test-caller-token-that-is-long-enough"})
                    response = connection.getresponse()
                    body = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    connection.close()

                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    connection.request("GET", f"/v1/sites/{OTHER}/switches/{SWITCH}/lldp-neighbors",
                                       headers={"Authorization": "Bearer test-caller-token-that-is-long-enough"})
                    response = connection.getresponse()
                    error = json.loads(response.read())
                    self.assertIn(response.status, (400, 404, 502))
                    self.assertEqual(error.get("error"), "site_ref_unknown")
                    connection.close()

                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    connection.request("POST", f"/v1/sites/{SITE}/switches/{SWITCH}/lldp-neighbors",
                                       body="{}", headers={"Authorization": "Bearer test-caller-token-that-is-long-enough",
                                                             "Content-Type": "application/json"})
                    response = connection.getresponse()
                    self.assertNotEqual(response.status, 200)
                    response.read()
                    connection.close()
                self.assertEqual(fake.calls, [(SITE, SWITCH), (OTHER, SWITCH)])
                self.assertEqual(body["resource"], "switch_lldp_neighbors")
                self.assertNotIn(SITE, captured.getvalue())
                self.assertNotIn(SWITCH, captured.getvalue())
                self.assertIn("<ref>", captured.getvalue())
            finally:
                client_patch.stop()
                env.stop()
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()


if __name__ == "__main__":
    unittest.main()
