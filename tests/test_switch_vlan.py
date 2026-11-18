from __future__ import annotations

import unittest
import json
import os
import tempfile
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.switch_vlan import SwitchVlanProjectionError, project_switch_networks_page


class SwitchVlanProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw_id = "private-network-id"
        self.ref = "a" * 24
        self.row = {
            "id": self.raw_id,
            "name": "private network name",
            "vlan": 140,
            "isolation": True,
            "portLagNetworkInfo": {
                "nativePorts": [1, 2], "tagPorts": [3], "untagPorts": [4],
                "nativeStPorts": ["1/0/1"], "tagStPorts": ["1/0/3"],
                "untagStPorts": ["1/0/4"], "nativeLags": [1], "tagLags": [2],
                "untagLags": [], "vlan": 140, "ipaddr": "192.0.2.4", "mode": 0,
            },
            "mac": "AA-BB-CC-DD-EE-FF", "password": "secret-value",
        }
        self.payload = {"errorCode": 0, "result": {
            "data": [self.row], "totalRows": 1, "currentPage": 1, "currentSize": 1,
        }}

    def test_projects_only_vlan_ports_and_callback_ref(self) -> None:
        calls: list[str] = []

        def ref_for(raw_id: str) -> str:
            calls.append(raw_id)
            return self.ref

        result = project_switch_networks_page(self.payload, ref_for, page=1, page_size=10)
        self.assertEqual(calls, [self.raw_id])
        self.assertEqual(result["items"], [{
            "network_ref": self.ref, "vlan_id": 140,
            "native_port_numbers": [1, 2], "tagged_port_numbers": [3],
            "untagged_port_numbers": [4],
        }])
        for private in (self.raw_id, "private network name", "192.0.2.4", "AA-BB-CC-DD-EE-FF",
                        "secret-value", "1/0/1", "ipaddr", "isolation"):
            self.assertNotIn(private, str(result))
        self.assertNotIn("link_status", result["items"][0])

    def test_accepts_nested_vlan_if_top_level_omitted(self) -> None:
        row = dict(self.row)
        row.pop("vlan")
        payload = {"errorCode": 0, "result": {"data": [row], "totalRows": 1,
            "currentPage": 1, "currentSize": 1}}
        result = project_switch_networks_page(payload, lambda _raw: self.ref,
                                               page=1, page_size=10)
        self.assertEqual(result["items"][0]["vlan_id"], 140)

    def test_pagination_is_strict_and_bounded(self) -> None:
        with self.assertRaisesRegex(SwitchVlanProjectionError, "pagination_invalid"):
            project_switch_networks_page(self.payload, lambda _raw: self.ref,
                                         page=2, page_size=10)
        with self.assertRaisesRegex(SwitchVlanProjectionError, "pagination_invalid"):
            project_switch_networks_page(self.payload, lambda _raw: self.ref,
                                         page=1, page_size=10, max_entries=0)
        oversized = {"errorCode": 0, "result": {"data": [], "totalRows": 257,
            "currentPage": 1, "currentSize": 0}}
        with self.assertRaisesRegex(SwitchVlanProjectionError, "pagination_invalid"):
            project_switch_networks_page(oversized, lambda _raw: self.ref,
                                         page=1, page_size=10)

    def test_rejects_bad_vlan_ports_ids_and_callback_refs(self) -> None:
        cases = [
            ({**self.row, "vlan": True}, "vlan_invalid"),
            ({**self.row, "vlan": 4095}, "vlan_invalid"),
            ({**self.row, "id": ""}, "row_invalid"),
            ({**self.row, "portLagNetworkInfo": {**self.row["portLagNetworkInfo"], "tagPorts": [0]}}, "ports_invalid"),
            ({**self.row, "portLagNetworkInfo": {**self.row["portLagNetworkInfo"], "nativePorts": [1, 1]}}, "ports_invalid"),
        ]
        for row, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(SwitchVlanProjectionError, error):
                project_switch_networks_page({"errorCode": 0, "result": {
                    "data": [row], "totalRows": 1, "currentPage": 1, "currentSize": 1}},
                    lambda _raw: self.ref, page=1, page_size=10)
        with self.assertRaisesRegex(SwitchVlanProjectionError, "reference_invalid"):
            project_switch_networks_page(self.payload, lambda _raw: "raw-network-id",
                                         page=1, page_size=10)

    def test_openapi_route_is_fixed_redacted_and_site_bound(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig("https://controller.example", "ctrl", "id", "secret",
                                                   cert_sha256="a" * 64, page_size=10, max_pages=2))
        site_a, site_b, switch_ref = "a" * 24, "b" * 24, "c" * 24
        client._site_ids_by_ref.update({site_a: "site_a", site_b: "site_b"})
        client._switch_macs_by_site_ref.update({
            site_a: {switch_ref: "AA-BB-CC-DD-EE-01"},
            site_b: {switch_ref: "AA-BB-CC-DD-EE-02"},
        })
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_pages", return_value=[self.row]) as read:
            result_a = client.read_switch_vlans(site_a, switch_ref)
            result_b = client.read_switch_vlans(site_b, switch_ref)
        read.assert_any_call("/openapi/v1/ctrl/sites/site_a/switches/AA-BB-CC-DD-EE-01/networks-detail", "token")
        read.assert_any_call("/openapi/v1/ctrl/sites/site_b/switches/AA-BB-CC-DD-EE-02/networks-detail", "token")
        self.assertNotEqual(result_a["items"][0]["network_ref"], result_b["items"][0]["network_ref"])
        self.assertEqual(result_a["switch_ref"], switch_ref)
        for private in (self.raw_id, "private network name", "192.0.2.4", "AA-BB-CC-DD-EE-FF", "secret-value"):
            self.assertNotIn(private, str(result_a))
        evidence = next(item for item in client.capabilities()["items"]
                        if item["operation"] == "switch_vlans")["runtime_evidence"]
        self.assertEqual(evidence[0]["target_ref"], site_a + ":" + switch_ref)
        with self.assertRaisesRegex(OpenApiError, "switch_ref_unknown"):
            client.read_switch_vlans(site_a, "d" * 24)

    def test_only_fixed_documented_networks_detail_get_path_passes(self) -> None:
        good = "/openapi/v1/ctrl/sites/site_1/switches/AA-BB-CC-DD-EE-FF/networks-detail?page=1&pageSize=50"
        with patch.object(OmadaOpenApiClient, "_connection", side_effect=OpenApiError("reached")):
            with self.assertRaisesRegex(OpenApiError, "reached"):
                self.client = OmadaOpenApiClient(OpenApiConfig("https://controller.example", "ctrl", "id", "secret",
                                                                 cert_sha256="a" * 64))
                self.client._request_json("GET", good)
            for path in (good + "&extra=1", good.replace("/networks-detail", "/networks-detail/private")):
                with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                    self.client._request_json("GET", path)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("POST", good)

    def test_authenticated_http_route_dispatches_and_scrubs_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token = "caller-token-0123456789abcdef0123456789"
            token_file = os.path.join(directory, "caller-token")
            with open(token_file, "w", encoding="utf-8") as handle:
                handle.write(token)
            class FakeClient:
                def __init__(self): self.calls = []
                def read_switch_vlans(self, site_ref, switch_ref):
                    self.calls.append((site_ref, switch_ref))
                    return {"status": "ok", "resource": "switch_vlans", "items": []}
            fake = FakeClient()
            with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_file}), \
                    patch.object(main, "_openapi_client", return_value=fake):
                server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    path = "/v1/sites/" + "a" * 24 + "/switches/" + "b" * 24 + "/vlans"
                    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    conn.request("GET", path)
                    unauthorized = conn.getresponse()
                    self.assertEqual(unauthorized.status, 401)
                    unauthorized.read()
                    conn.close()
                    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    conn.request("GET", path, headers={"Authorization": "Bearer " + token})
                    response = conn.getresponse()
                    body = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertEqual(body["resource"], "switch_vlans")
                    conn.close()
                    self.assertEqual(fake.calls, [("a" * 24, "b" * 24)])
                finally:
                    server.shutdown(); thread.join(timeout=2); server.server_close()


if __name__ == "__main__":
    unittest.main()
