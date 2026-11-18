from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SwitchPortReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.switch_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._switch_macs_by_site_ref[self.site_ref] = {
            self.switch_ref: "00:11:22:33:44:55"}

    def test_inventory_maps_explicit_switch_type_only(self) -> None:
        self.client._read_pages = lambda *_args: [
            {"deviceId": "sw-id", "type": "Switch", "mac": "00-11-22-33-44-55", "name": "private"},
            {"deviceId": "unknown", "type": "unknown", "mac": "00-11-22-33-44-66"},
        ]  # type: ignore[method-assign]
        with patch.object(self.client, "_access_token", return_value="token"):
            result = self.client.list_devices(self.site_ref)
        self.assertNotIn("private", str(result))
        self.assertEqual(list(self.client._switch_macs_by_site_ref[self.site_ref].values()),
                         ["00-11-22-33-44-55"])

    def test_returns_port_and_link_poe_values_only_for_selected_switch(self) -> None:
        rows = [
            {"port": 3, "switchMac": "00:11:22:33:44:55", "portName": "private",
             "switchName": "private", "site": "private", "ip": "192.0.2.1",
             "connectedStatus": 0, "supportPoe": True, "poe": 1,
             "portStatus": {"port": 3, "linkStatus": 1, "linkSpeed": 3,
                            "duplex": 2, "poe": True, "poePower": 5.25,
                            "chassisId": "private"}},
            {"port": 4, "switchMac": "00:11:22:33:44:66", "portStatus": {}},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows) as read:
            result = self.client.read_switch_ports(self.site_ref, self.switch_ref)
        read.assert_called_once_with("/openapi/v1/ctrl/sites/site_1/switches/ports/overview", "token")
        self.assertEqual(result["items"], [{"port": 3, "connected_status": 0,
            "poe_mode": 1, "poe_supported": True, "link_status": 1,
            "link_speed": 3, "duplex": 2, "poe_active": True, "poe_power_w": 5.25}])
        self.assertNotIn("private", str(result))
        evidence = next(x for x in self.client.capabilities()["items"]
                        if x["operation"] == "switch_ports")["runtime_evidence"]
        self.assertEqual(evidence[0]["target_ref"], self.site_ref + ":" + self.switch_ref)

    def test_unknown_switch_and_malformed_status_fail(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
            self.client.read_switch_ports(self.site_ref, "c" * 24)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=[
                    {"port": 1, "switchMac": "00:11:22:33:44:55", "portStatus": {"linkStatus": "up"}}]):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_switch_ports(self.site_ref, self.switch_ref)

    def test_fixed_read_path_allowlist(self) -> None:
        good = "/openapi/v1/ctrl/sites/site_1/switches/ports/overview?page=1&pageSize=100"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good + "&evil=true")


if __name__ == "__main__":
    unittest.main()
