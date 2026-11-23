from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_vlan_topology_summary import (
    SiteVlanTopologyError, summarize_site_vlan_topology,
)


class SiteVlanTopologySummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.network_ref = "9" * 24
        self.device_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_matches_topology_macs_only_to_the_same_site_inventory(self):
        result = summarize_site_vlan_topology(
            {"deviceMacs": ["AA-BB-CC-DD-EE-01", "AA-BB-CC-DD-EE-02"]},
            inventory_mac_by_ref={self.device_ref: "aa:bb:cc:dd:ee:01"},
            inventory_type_by_ref={self.device_ref: "switch"})
        self.assertEqual(result["device_class_counts"]["switch"], 1)
        self.assertEqual(result["unmatched_topology_device_count"], 1)
        self.assertTrue(result["partial"])
        for secret in ("AA-BB-CC-DD-EE-01", self.device_ref):
            self.assertNotIn(secret, repr(result))

    def test_unexpected_topology_fields_are_partial_and_shape_is_checked(self):
        result = summarize_site_vlan_topology(
            {"deviceMacs": [], "future": True},
            inventory_mac_by_ref={}, inventory_type_by_ref={})
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        with self.assertRaises(SiteVlanTopologyError):
            summarize_site_vlan_topology([], inventory_mac_by_ref={},
                                         inventory_type_by_ref={})

    def test_network_and_vlan_are_bound_before_fixed_topology_read(self):
        def networks(site_ref):
            self.client._network_ids_by_site_ref[site_ref] = {self.network_ref: "network_internal"}
            return {"items": [{"network_ref": self.network_ref, "purpose": 0, "vlan": 23}]}

        def devices(site_ref):
            self.client._inventory_macs_by_site_ref[site_ref] = {
                self.device_ref: "AA-BB-CC-DD-EE-01"}
            return {"items": [{"device_ref": self.device_ref, "device_type": "switch"}]}

        with patch.object(self.client, "list_networks", side_effect=networks), \
                patch.object(self.client, "list_devices", side_effect=devices), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"deviceMacs": ["AA-BB-CC-DD-EE-01"]}}) as request:
            result = self.client.read_site_vlan_topology_summary(
                self.site_ref, self.network_ref, 23)
        request.assert_called_once_with(
            "GET", "/openapi/v3/ctrl/sites/site_internal/topology/network_internal/vlan/23/devices",
            token="token")
        self.assertEqual(result["device_class_counts"]["switch"], 1)
        self.assertTrue(self.client._site_vlan_topology_request_valid(
            "/openapi/v3/ctrl/sites/site_internal/topology/network_internal/vlan/23/devices"))
        self.assertFalse(self.client._site_vlan_topology_request_valid(
            "/openapi/v3/other/sites/site_internal/topology/network_internal/vlan/23/devices"))
        with patch.object(self.client, "list_networks", side_effect=networks):
            with self.assertRaisesRegex(OpenApiError, "network_vlan_mismatch"):
                self.client.read_site_vlan_topology_summary(
                    self.site_ref, self.network_ref, 24)


if __name__ == "__main__":
    unittest.main()
