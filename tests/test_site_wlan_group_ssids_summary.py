from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wlan_group_ssids_summary import (
    SiteWlanGroupSsidsSummaryError, project_site_wlan_group_ssids,
)


def ssid(**changes):
    row = {"ssidId": "private-ssid-id", "id": "private-ssid-id-2",
           "name": "private-network-name", "description": True,
           "chooseDevices": 1, "band": 7, "guestNetEnable": False,
           "security": 3, "broadcast": True, "vlanEnable": True,
           "vlanId": 17, "vlanPoolIds": "private-pool"}
    row.update(changes)
    return row


def page(number, total, rows):
    return {"totalRows": total, "currentPage": number,
            "currentSize": len(rows), "data": rows}


class SiteWlanGroupSsidsProjectionTests(unittest.TestCase):
    def test_counts_common_wireless_flags_band_and_security_without_names(self):
        result = project_site_wlan_group_ssids([
            page(1, 2, [ssid(), ssid(band=1, security=5, description=False)])])
        data = result["data"]
        self.assertEqual(data["returned_ssid_count"], 2)
        self.assertEqual(data["band_coverage_counts"], {
            "2.4GHz": 2, "5GHz": 1, "6GHz": 1})
        self.assertEqual(data["security_code_counts"], {"0": 0, "2": 0,
                         "3": 1, "4": 0, "5": 1})
        self.assertEqual(data["ssid_flag_counts"]["ssid_enabled"], {
            "enabled_count": 1, "disabled_count": 1, "unreported_count": 0})
        self.assertNotIn("private", repr(result))
        self.assertFalse(result["partial"])

    def test_missing_unknown_and_truncated_results_are_reported(self):
        result = project_site_wlan_group_ssids([
            page(1, 1, [ssid(band=15, security=99, broadcast="yes",
                             unknown="private")])])
        self.assertTrue(result["partial"])
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertGreater(result["unknown_field_count"], 0)
        self.assertEqual(result["data"]["unknown_band_code_count"], 1)
        truncated = project_site_wlan_group_ssids([
            page(i, 600, [ssid()] * 100) for i in range(1, 6)])
        self.assertTrue(truncated["data"]["truncated"])
        self.assertEqual(truncated["data"]["returned_ssid_count"], 500)
        with self.assertRaises(SiteWlanGroupSsidsSummaryError):
            project_site_wlan_group_ssids([])


class SiteWlanGroupSsidsClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "e" * 24
        self.group_ref = "f" * 24
        self.client._site_ids_by_ref[self.site_ref] = "internal_site"
        self.client._wlan_group_ids_by_site_ref[self.site_ref] = {
            self.group_ref: "internal_wlan_group"}

    def test_reads_ssids_for_current_inventory_group_reference(self):
        response = {"result": page(1, 1, [ssid()])}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=response) as request:
            result = self.client.read_site_wlan_group_ssids_summary(
                self.site_ref, self.group_ref)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[1],
                         "/openapi/v1/ctrl/sites/internal_site/wireless-network/"
                         "wlans/internal_wlan_group/ssids?page=1&pageSize=100")
        self.assertEqual(result["data"]["returned_ssid_count"], 1)

    def test_fresh_wlan_group_inventory_supplies_the_opaque_group_reference(self):
        inventory = {"result": {"gridWlanGroup": {
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"id": "inventory_wlan_id", "primary": True,
                      "clone": False, "resource": 0}],
        }}}
        ssids = {"result": page(1, 1, [ssid()])}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json",
                             side_effect=[inventory, ssids]) as request:
            listing = self.client.list_wlan_groups(self.site_ref)
            group_ref = listing["items"][0]["group_ref"]
            result = self.client.read_site_wlan_group_ssids_summary(self.site_ref, group_ref)
        self.assertEqual(self.client._wlan_group_ids_by_site_ref[self.site_ref][group_ref],
                         "inventory_wlan_id")
        self.assertNotEqual(group_ref, "inventory_wlan_id")
        self.assertEqual(result["data"]["returned_ssid_count"], 1)
        self.assertIn("inventory_wlan_id", request.call_args.args[1])

    def test_rejects_unknown_group_reference_and_guards_controller_path(self):
        path = ("/openapi/v1/ctrl/sites/internal_site/wireless-network/wlans/"
                "internal_wlan_group/ssids?page=1&pageSize=100")
        self.assertTrue(self.client._site_wlan_group_ssids_request_valid(path))
        self.assertFalse(self.client._site_wlan_group_ssids_request_valid(
            path.replace("/ctrl/", "/other/")))
        with self.assertRaisesRegex(OpenApiError, "wlan_group_ref_unknown"):
            self.client.read_site_wlan_group_ssids_summary(self.site_ref, "a" * 24)


if __name__ == "__main__":
    unittest.main()
