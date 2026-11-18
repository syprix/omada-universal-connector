from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_mac_auth_ssid_inventory import (
    MacAuthSsidInventoryError, summarize_mac_auth_ssid_inventory,
)


class MacAuthSsidInventoryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_projects_names_and_omits_all_identifiers(self):
        result = summarize_mac_auth_ssid_inventory([
            {"wlanId": "private-wlan", "wlanName": "Office",
             "ssidList": [{"id": "private-id", "ssidId": "legacy-id",
                           "ssidName": "Staff"}, {"ssidName": "Guest"}]},
        ], device_type=3)
        self.assertEqual(result["device_type"], 3)
        self.assertEqual(result["wlan_count"], 1)
        self.assertEqual(result["ssid_count"], 2)
        self.assertEqual(result["items"], [
            {"wlan_name": "Office", "ssid_names": ["Staff", "Guest"]}])
        self.assertFalse(result["partial"])
        for identifier in ("private-wlan", "private-id", "legacy-id"):
            self.assertNotIn(identifier, repr(result))

    def test_malformed_unknown_and_truncated_records_are_partial(self):
        bad = summarize_mac_auth_ssid_inventory([
            {"wlanName": "Valid", "ssidList": [{"ssidName": "Bad\nName"}],
             "future": True},
            None,
        ], device_type=1)
        self.assertTrue(bad["partial"])
        self.assertEqual(bad["invalid_field_count"], 2)
        self.assertEqual(bad["unknown_field_count"], 1)
        large = summarize_mac_auth_ssid_inventory([
            {"wlanName": "WLAN", "ssidList":[{"ssidName": f"SSID{i}"}
                                                    for i in range(501)]},
        ], device_type=2)
        self.assertEqual(large["ssid_count"], 501)
        self.assertEqual(large["returned_ssid_count"], 500)
        self.assertTrue(large["partial"])
        with self.assertRaises(MacAuthSsidInventoryError):
            summarize_mac_auth_ssid_inventory([], device_type=4)

    def test_fixed_site_path_requires_valid_device_type(self):
        payload = {"result": [{"wlanName": "Office", "ssidList": []}]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_site_mac_auth_ssid_inventory(self.site_ref, 3)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/wireless-network/ssids?type=3",
            token="token")
        self.assertEqual(result["wlan_count"], 1)
        path = "/openapi/v1/ctrl/sites/site_internal/wireless-network/ssids?type=3"
        self.assertTrue(self.client._site_mac_auth_ssid_inventory_request_valid(path))
        self.assertFalse(self.client._site_mac_auth_ssid_inventory_request_valid(
            path.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_mac_auth_ssid_inventory_request_valid(
            path.replace("type=3", "type=4")))
        with self.assertRaisesRegex(OpenApiError, "query_invalid"):
            self.client.read_site_mac_auth_ssid_inventory(self.site_ref, 4)


if __name__ == "__main__":
    unittest.main()
