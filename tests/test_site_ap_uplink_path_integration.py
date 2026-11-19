from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteApUplinkPathIntegrationTests(unittest.TestCase):
    def test_refreshes_inventory_and_joins_two_read_sources_per_selected_ap(self):
        site_ref, ap_a, ap_b, switch = "a" * 24, "b" * 24, "c" * 24, "d" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site-internal"
        calls = []

        def inventory(site):
            self.assertEqual(site, site_ref)
            client._device_macs_by_site_ref[site_ref] = {
                ap_a: "00-11-22-33-44-01", ap_b: "00-11-22-33-44-02"}
            client._inventory_macs_by_site_ref[site_ref] = {
                ap_a: "00-11-22-33-44-01", ap_b: "00-11-22-33-44-02",
                switch: "00-11-22-33-44-03"}
            return {"status": "ok", "items": [
                {"device_ref": ap_a, "device_type": "AP", "state": 1},
                {"device_ref": ap_b, "device_type": "AP", "state": 1},
                {"device_ref": switch, "device_type": "Switch", "state": 1},
            ]}

        def wired(_site, ref, *, include_inventory_reference=False):
            calls.append(("wired", ref, include_inventory_reference))
            if ref == ap_a:
                return {"status": "ok", "data": {"wiredUplink": {
                    "rate_mbps": 1000, "uplink_device_ref_status": "mapped",
                    "uplink_device_ref": switch}}}
            return {"status": "ok", "data": {"wiredUplink": {"rate_mbps": 0}}}

        def mesh(_site, ref, *, include_parent_reference=False):
            calls.append(("mesh", ref, include_parent_reference))
            return {"status": "ok", "resource": "ap_mesh_statistics", "data": {
                "wireless_linked": ref == ap_b,
                "wireless_uplink": ({"uplink_ap_ref_status": "mapped",
                                     "uplink_ap_ref": ap_a, "rssi": -58,
                                     "snr": 31, "tx_rate_mbps": 500}
                                    if ref == ap_b else {})}}

        with patch.object(client, "list_devices", side_effect=inventory), \
                patch.object(client, "read_ap_wired_uplink", side_effect=wired), \
                patch.object(client, "read_ap_mesh_statistics", side_effect=mesh):
            result = client.read_site_ap_uplink_path_summary(site_ref, [ap_a, ap_b])

        self.assertEqual(calls, [
            ("wired", ap_a, True), ("mesh", ap_a, True),
            ("wired", ap_b, True), ("mesh", ap_b, True),
        ])
        self.assertEqual(result["aps"][0]["path"]["next_hop_ref"], switch)
        self.assertEqual(result["aps"][1]["path"]["next_hop_ref"], ap_a)
        self.assertEqual(result["aps"][1]["path"]["continuation"],
                         "selected_device_included")
        self.assertFalse(result["partial"])


if __name__ == "__main__":
    unittest.main()
