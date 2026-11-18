from __future__ import annotations

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


class MeshIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.ap_ref = "a" * 24, "b" * 24
        self.mac = "AA-BB-CC-DD-EE-FF"
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._device_macs_by_site_ref[self.site_ref] = {self.ap_ref: self.mac}

    def test_known_ap_get_path_and_projection_redact_identifiers(self) -> None:
        payload = {"result": {
            "status": 72, "statusCategory": -2, "wirelessLinked": True, "scanStatus": 2,
            "wirelessUplink": {"uplinkMac": "00:11:22:33:44:55", "name": "private AP",
                "ip": "192.0.2.2", "channel": 44, "rssi": -61, "snr": 31,
                "txRate": "private rate", "txRateInt": 866},
            "childAps": [{"mac": "00:11:22:33:44:66", "name": "private child",
                          "ip": "192.0.2.3", "rssi": -70}],
            "candidateParents": [{"mac": "00:11:22:33:44:77", "name": "private parent",
                "linkStatus": 2, "hop": 1, "childsnum": 3,
                "multiBandInfo": [{"radioId": 1, "channel": 36, "rssi": -65}]}],
            "private": "secret text",
        }}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_ap_mesh_statistics(self.site_ref, self.ap_ref)
        request.assert_called_once_with("GET",
            f"/openapi/v1/ctrl/sites/site_1/aps/{self.mac}/mesh/statistics", token="token")
        self.assertEqual(result["resource"], "ap_mesh_statistics")
        self.assertEqual(result["data"]["wireless_uplink"]["tx_rate_mbps"], 866)
        self.assertEqual(result["data"]["candidate_parents"][0]["link_status"], 2)
        for private in (self.mac, "00:11:22:33:44:55", "00:11:22:33:44:66", "00:11:22:33:44:77",
                        "private AP", "private child", "private parent", "192.0.2.2", "private rate", "secret text"):
            self.assertNotIn(private, str(result))
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "ap_mesh_statistics")["runtime_evidence"]
        self.assertEqual(evidence[0]["target_ref"], self.site_ref + ":" + self.ap_ref)

    def test_unknown_ap_ref_is_rejected_before_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
                self.client.read_ap_mesh_statistics(self.site_ref, "c" * 24)
        request.assert_not_called()

    def test_msp_mesh_read_reuses_redacted_projection_and_binds_known_ap(self) -> None:
        payload = {"result": {"status": 4, "wirelessLinked": True,
                              "wirelessUplink": {"name": "private AP", "ip": "192.0.2.8",
                                                "uplinkMac": "00:11:22:33:44:55", "rssi": -60}}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_msp_ap_mesh_statistics(
                "msp-1", "customer-2", self.site_ref, self.ap_ref)
        request.assert_called_once_with(
            "GET", f"/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/aps/{self.mac}/mesh/statistics",
            token="token")
        self.assertEqual(result["resource"], "msp_ap_mesh_statistics")
        self.assertEqual(result["data"]["status"], 4)
        for private in (self.mac, "private AP", "192.0.2.8", "00:11:22:33:44:55"):
            self.assertNotIn(private, str(result))

    def test_msp_mesh_fixed_read_allowlist(self) -> None:
        good = f"/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/aps/{self.mac}/mesh/statistics"
        self.assertTrue(self.client._msp_ap_mesh_statistics_request_valid(good))
        self.assertFalse(self.client._msp_ap_mesh_statistics_request_valid(good + "?raw=true"))
        self.assertFalse(self.client._msp_ap_mesh_statistics_request_valid(good.replace("msp-1", "../x")))
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)

    def test_upstream_allowlist_is_exact_get_only(self) -> None:
        good = f"/openapi/v1/ctrl/sites/site_1/aps/{self.mac}/mesh/statistics"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
            for path in (good + "?raw=true", good + "/scan", good.replace("/mesh/statistics", "/mesh")):
                with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                    self.client._request_json("GET", path)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("POST", good)

    def test_http_route_rejects_missing_auth_and_dispatches_known_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token = "caller-token-0123456789abcdef0123456789"
            token_file = os.path.join(directory, "token")
            with open(token_file, "w", encoding="utf-8") as handle:
                handle.write(token)

            class FakeClient:
                def __init__(self): self.calls = []
                def read_ap_mesh_statistics(self, site_ref, device_ref):
                    self.calls.append((site_ref, device_ref))
                    return {"status": "ok", "resource": "ap_mesh_statistics", "data": {"status": 1}}

            fake = FakeClient()
            with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_file}), \
                    patch.object(main, "_openapi_client", return_value=fake):
                server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    path = f"/v1/sites/{self.site_ref}/aps/{self.ap_ref}/mesh"
                    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    conn.request("GET", path)
                    denied = conn.getresponse()
                    self.assertEqual(denied.status, 401)
                    denied.read(); conn.close()
                    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    conn.request("GET", path, headers={"Authorization": "Bearer " + token})
                    response = conn.getresponse()
                    body = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertEqual(body["resource"], "ap_mesh_statistics")
                    conn.close()
                    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": "omada_ap_mesh_statistics",
                                          "arguments": {"site_ref": self.site_ref,
                                                        "device_ref": self.ap_ref}}}
                    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    conn.request("POST", "/mcp", body=json.dumps(request), headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                    })
                    response = conn.getresponse()
                    mcp_body = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertEqual(
                        mcp_body["result"]["structuredContent"]["resource"],
                        "ap_mesh_statistics")
                    conn.close()
                    self.assertEqual(fake.calls, [(self.site_ref, self.ap_ref)] * 2)
                finally:
                    server.shutdown(); thread.join(timeout=2); server.server_close()


if __name__ == "__main__":
    unittest.main()
