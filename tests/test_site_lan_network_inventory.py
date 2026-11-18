from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_lan_network_inventory import (
    LanNetworkInventoryError, summarize_lan_network_inventory,
)


class LanNetworkInventoryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_projects_only_bounded_counts_from_documented_rows(self):
        result = summarize_lan_network_inventory([
            {"id": "private", "site": "private", "name": "Office",
             "purpose": "vlan", "vlan": 27, "gatewaySubnet": "10.0.0.1/24",
             "dhcpSettings": {"enable": True, "priDns": "private"},
             "isolation": False, "igmpSnoopEnable": True},
            {"name": "Guest", "purpose": "interface",
             "dhcpSettings": {"enable": False}, "portal": True},
        ])
        self.assertEqual(result["network_count"], 2)
        self.assertEqual(result["purpose_counts"], {"vlan": 1, "interface": 1})
        self.assertEqual(result["records_with_vlan_id_count"], 1)
        self.assertEqual(result["dhcp_server"]["enabled_count"], 1)
        self.assertEqual(result["dhcp_server"]["disabled_count"], 1)
        self.assertFalse(result["partial"])
        for secret in ("private", "10.0.0.1", "Office", "Guest"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_rows_unknown_fields_and_truncation_are_partial(self):
        invalid = summarize_lan_network_inventory([
            {"purpose": "unexpected", "newField": True}, None,
        ])
        self.assertTrue(invalid["partial"])
        self.assertEqual(invalid["invalid_record_count"], 2)
        self.assertEqual(invalid["unknown_field_count"], 1)
        large = summarize_lan_network_inventory(
            [{"purpose": "vlan"}] * 3, max_items=2)
        self.assertTrue(large["partial"])
        self.assertEqual(large["returned_count"], 2)
        with self.assertRaises(LanNetworkInventoryError):
            summarize_lan_network_inventory({"result": []})

    def test_fixed_site_bound_path_and_response_projection(self):
        payload = {"result": [{"purpose": "vlan", "vlan": 27,
                               "gatewaySubnet": "10.0.0.1/24"}]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_site_lan_network_inventory(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/lan-networks/all",
            token="token")
        self.assertEqual(result["network_count"], 1)
        self.assertNotIn("gatewaySubnet", repr(result))
        path = "/openapi/v1/ctrl/sites/site_internal/lan-networks/all"
        self.assertTrue(self.client._site_lan_network_inventory_request_valid(path))
        self.assertFalse(self.client._site_lan_network_inventory_request_valid(path + "?page=1"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_lan_network_inventory("7" * 24)


if __name__ == "__main__":
    unittest.main()
