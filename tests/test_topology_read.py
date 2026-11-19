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


class TopologyReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.switch_mac = "AA-BB-CC-DD-EE-01"
        self.ap_mac = "AA-BB-CC-DD-EE-02"
        self.switch_device_ref = "1" * 24
        self.ap_device_ref = "2" * 24
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.switch_device_ref: self.switch_mac, self.ap_device_ref: self.ap_mac}
        self.client._switch_macs_by_site_ref[self.site_ref] = {self.switch_device_ref: self.switch_mac}
        self.client._device_macs_by_site_ref[self.site_ref] = {self.ap_device_ref: self.ap_mac}
        self.stack_summary_patch = patch.object(
            self.client, "read_site_stack_connections_summary",
            return_value={"status": "ok", "resource": "site_stack_connections_summary",
                          "partial": False, "data": {"stacks": []}})
        self.stack_summary_patch.start()
        self.addCleanup(self.stack_summary_patch.stop)

    def topology_payload(self):
        return {"result": {"lastUpdateTime": 1_800_000_000_000, "topologyArray": [{
            "type": "switch", "name": "private-switch-name", "mac": self.switch_mac,
            "ip": "192.0.2.10", "status": 9001, "disconnected": False, "active": True,
            "successors": [{"type": "ap", "name": "private-ap-name", "mac": self.ap_mac,
                "ip": "192.0.2.11", "disconnected": True, "active": True,
                "successors": [{"type": "other", "mac": "AA-BB-CC-DD-EE-03",
                                "name": "private-other"}]}]},
            {"type": "switch", "mac": "AA-BB-CC-DD-EE-03", "successors": []},
        ]}}

    def test_topology_projects_only_inventory_refs_status_and_edges(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=self.topology_payload()) as request:
            result = self.client.read_site_topology(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v3/ctrl/sites/site_1/topology?filters.deviceStatus=0%2C1", token="token")
        self.assertEqual(result["resource"], "site_topology")
        self.assertEqual(result["stack_connections"]["resource"],
                         "site_stack_connections_summary")
        self.assertEqual(len(result["nodes"]), 2)
        nodes = {node["device_type"]: node for node in result["nodes"]}
        self.assertEqual(nodes["switch"]["disconnected"], False)
        self.assertEqual(nodes["ap"]["disconnected"], True)
        self.assertEqual(nodes["switch"]["license_active"], True)
        self.assertNotIn("active", nodes["switch"])
        self.assertEqual(nodes["switch"]["device_ref"], self.switch_device_ref)
        self.assertEqual(nodes["ap"]["device_ref"], self.ap_device_ref)
        self.assertEqual(result["edges"], [{"from_device_ref": nodes["switch"]["device_ref"],
                                          "to_device_ref": nodes["ap"]["device_ref"]}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_node_count"], 2)
        self.assertEqual(result["omitted_edge_count"], 1)
        for private in (self.switch_mac, self.ap_mac, "192.0.2.10", "192.0.2.11",
                        "private-switch-name", "private-ap-name", "private-other", "9001"):
            self.assertNotIn(private, str(result))
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "site_topology")["runtime_evidence"]
        self.assertEqual(evidence[0]["target_ref"], self.site_ref)

    def test_topology_refs_are_site_inventory_refs_and_inventory_is_required(self) -> None:
        site_b = "b" * 24
        self.client._site_ids_by_ref[site_b] = "site_2"
        switch_ref_b, ap_ref_b = "3" * 24, "4" * 24
        self.client._inventory_macs_by_site_ref[site_b] = {
            switch_ref_b: self.switch_mac, ap_ref_b: self.ap_mac}
        self.client._switch_macs_by_site_ref[site_b] = {switch_ref_b: self.switch_mac}
        self.client._device_macs_by_site_ref[site_b] = {ap_ref_b: self.ap_mac}
        payload = self.topology_payload()
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload):
            a = self.client.read_site_topology(self.site_ref)
            b = self.client.read_site_topology(site_b)
        self.assertEqual({node["device_ref"] for node in a["nodes"]},
                         {self.switch_device_ref, self.ap_device_ref})
        self.assertEqual({node["device_ref"] for node in b["nodes"]},
                         {switch_ref_b, ap_ref_b})
        site_c = "c" * 24
        self.client._site_ids_by_ref[site_c] = "site_3"
        with self.assertRaisesRegex(OpenApiError, "device_inventory_required"):
            self.client.read_site_topology(site_c)

    def test_ambiguous_inventory_mac_is_omitted_and_marked_partial(self) -> None:
        self.client._inventory_macs_by_site_ref[self.site_ref]["5" * 24] = self.switch_mac
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=self.topology_payload()):
            result = self.client.read_site_topology(self.site_ref)
        self.assertEqual({node["device_ref"] for node in result["nodes"]}, {self.ap_device_ref})
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_node_count"], 3)
        self.assertEqual(result["omitted_edge_count"], 2)

    def test_skipped_self_edge_is_counted_as_partial(self) -> None:
        payload = {"result": {"topologyArray": [{
            "type": "switch", "mac": self.switch_mac,
            "successors": [{"type": "switch", "mac": self.switch_mac}],
        }]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload):
            result = self.client.read_site_topology(self.site_ref)
        self.assertEqual(len(result["nodes"]), 1)
        self.assertEqual(result["edges"], [])
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_edge_count"], 1)

    def test_topology_reports_incomplete_stack_coverage(self) -> None:
        self.stack_summary_patch.stop()
        self.stack_summary_patch = patch.object(
            self.client, "read_site_stack_connections_summary",
            return_value={"status": "partial", "resource": "site_stack_connections_summary",
                          "partial": True, "data": {"stacks": []}})
        self.stack_summary_patch.start()
        self.addCleanup(self.stack_summary_patch.stop)
        payload = {"result": {"topologyArray": [
            {"type": "switch", "mac": self.switch_mac, "successors": []}]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload):
            result = self.client.read_site_topology(self.site_ref)
        self.assertTrue(result["partial"])
        self.assertEqual(result["stack_connections"]["status"], "partial")

    def test_malformed_schema_or_unbounded_arrays_fail_closed(self) -> None:
        payload = self.topology_payload()
        payload["result"]["topologyArray"][0]["disconnected"] = 1
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_topology(self.site_ref)
        payload = self.topology_payload()
        payload["result"]["topologyArray"] = [payload["result"]["topologyArray"][0]] * 1001
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_topology(self.site_ref)

    def test_only_exact_fixed_status_filter_get_is_allowed(self) -> None:
        good = "/openapi/v3/ctrl/sites/site_1/topology?filters.deviceStatus=0%2C1"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
            for path in (good + "&x=1", good.replace("0%2C1", "0"),
                         good.replace("/openapi/v3/", "/openapi/v2/")):
                with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                    self.client._request_json("GET", path)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("PATCH", good)

    def test_caller_authentication_and_route_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token = "caller-token-0123456789abcdef0123456789"
            token_file = os.path.join(directory, "token")
            with open(token_file, "w", encoding="utf-8") as handle:
                handle.write(token)

            class FakeClient:
                def __init__(self): self.calls = []
                def read_site_topology(self, site_ref):
                    self.calls.append(site_ref)
                    return {"status": "ok", "resource": "site_topology", "nodes": [], "edges": []}

            fake = FakeClient()
            with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_file}), \
                    patch.object(main, "_openapi_client", return_value=fake):
                server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    path = "/v1/sites/" + "a" * 24 + "/topology"
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
                    self.assertEqual(body["resource"], "site_topology")
                    conn.close()
                    self.assertEqual(fake.calls, ["a" * 24])
                finally:
                    server.shutdown(); thread.join(timeout=2); server.server_close()


if __name__ == "__main__":
    unittest.main()
