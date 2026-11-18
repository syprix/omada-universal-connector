from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class GatewayWanReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.gateway_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._gateway_macs_by_site_ref[self.site_ref] = {
            self.gateway_ref: "00:11:22:33:44:55"}

    def test_inventory_maps_only_known_gateway_and_sanitizes_status(self) -> None:
        self.client._read_pages = lambda *_args: [
            {"deviceId": "gw-id", "type": "Gateway", "mac": "00-11-22-33-44-55",
             "name": "private", "ip": "192.0.2.1"},
            {"deviceId": "maybe", "type": "unknown", "mac": "00-11-22-33-44-66"},
        ]  # type: ignore[method-assign]
        with patch.object(self.client, "_access_token", return_value="token"):
            inventory = self.client.list_devices(self.site_ref)
        self.assertNotIn("private", str(inventory))
        self.assertNotIn("192.0.2.1", str(inventory))
        mapping = self.client._gateway_macs_by_site_ref[self.site_ref]
        self.assertEqual(list(mapping.values()), ["00-11-22-33-44-55"])

    def test_returns_typed_safe_link_health_fields_using_inventory_mac(self) -> None:
        calls = []
        payload = {"result": [
            {"port": 1, "name": "private", "mac": "aa:bb", "ip": "192.0.2.2",
             "status": 1, "internetState": 1, "speed": 3, "duplex": 2,
             "rx": 12, "txRate": 4, "latency": 25, "loss": 0.5,
             "healthLevel": 2, "isp": "private"}
        ]}
        def request(method, path, **kwargs):
            calls.append((method, path))
            return payload
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_gateway_wan_status(self.site_ref, self.gateway_ref)
        self.assertEqual(calls[0][0], "GET")
        self.assertIn("00:11:22:33:44:55/wan-status", calls[0][1])
        self.assertEqual(result["items"], [{"port": 1, "link_status": 1,
            "internet_state": 1, "speed": 3, "duplex": 2, "rx_bytes": 12,
            "tx_rate_kb_s": 4, "latency_ms": 25, "loss_percent": 0.5,
            "health_level": 2}])
        self.assertNotIn("private", str(result))
        evidence = next(x for x in self.client.capabilities()["items"]
                        if x["operation"] == "gateway_wan_status")["runtime_evidence"]
        self.assertEqual(evidence[0]["target_ref"], self.site_ref + ":" + self.gateway_ref)

    def test_unknown_gateway_and_invalid_schema_rejected(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
            self.client.read_gateway_wan_status(self.site_ref, "c" * 24)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": [{"status": "up"}]}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_gateway_wan_status(self.site_ref, self.gateway_ref)

    def test_fixed_read_path_allowlist(self) -> None:
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", "/openapi/v1/ctrl/sites/site_1/gateways/00-11-22-33-44-55/wan-status")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", "/openapi/v1/ctrl/sites/site_1/gateways/anything/wan-status")


if __name__ == "__main__":
    unittest.main()
