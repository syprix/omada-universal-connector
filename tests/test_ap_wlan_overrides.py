from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_wlan_overrides import ApWlanOverridesError, summarize_ap_wlan_overrides
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ApWlanOverridesProjectionTests(unittest.TestCase):
    def test_counts_configuration_and_redacts_wlan_values(self):
        result = summarize_ap_wlan_overrides({
            "apGroupId": "private-group-id", "apGroupName": "private-group-name",
            "ssidOverrides": [{
                "ssidId": "private-ssid-id", "ssidName": "private-ssid",
                "ssidPassword": "private-password", "ssidEntryId": 17,
                "band": [0, 1, 2], "security": 3,
                "vlanEnable": True, "vlanId": 177, "vlanPoolIds": "private-pool",
                "ssidEnable": True,
            }, {"ssidId": "other-id", "ssidName": "other", "ssidEnable": False,
                "vlanEnable": False, "security": 0, "band": [1]}],
        })
        self.assertEqual(result["entry_count"], 2)
        self.assertEqual(result["enabled_count"], 1)
        self.assertEqual(result["disabled_count"], 1)
        self.assertEqual(result["vlan_enabled_count"], 1)
        self.assertEqual(result["password_present_count"], 1)
        self.assertEqual(result["vlan_id_present_count"], 1)
        self.assertEqual(result["by_band_code"], {0: 1, 1: 2, 2: 1})
        for value in ("private-group-id", "private-group-name", "private-ssid-id",
                      "private-ssid", "private-password", "private-pool", "177"):
            self.assertNotIn(value, repr(result))
        self.assertFalse(result["partial"])

    def test_missing_state_and_unknown_fields_are_partial_but_redacted(self):
        result = summarize_ap_wlan_overrides({"ssidOverrides": [{
            "ssidId": "private", "ssidName": "private-name", "futureSecret": "secret",
        }]})
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["unknown_enabled_state_count"], 1)
        self.assertEqual(result["unknown_vlan_state_count"], 1)
        self.assertNotIn("secret", repr(result))
        self.assertTrue(result["partial"])

    def test_invalid_rows_and_fields_are_counted_without_echo(self):
        result = summarize_ap_wlan_overrides({"ssidOverrides": [
            {"ssidId": "id", "ssidName": "name", "ssidEnable": 1,
             "vlanEnable": True, "band": [9], "security": 99,
             "ssidPassword": "short", "vlanId": True},
            "private-row",
        ]})
        self.assertEqual(result["invalid_field_count"], 5)
        self.assertEqual(result["invalid_row_count"], 1)
        self.assertNotIn("short", repr(result))
        self.assertNotIn("private-row", repr(result))
        self.assertTrue(result["partial"])

    def test_over_limit_entries_are_truncated_and_reported(self):
        rows = [{"ssidId": "id", "ssidName": "name", "ssidEnable": True,
                 "vlanEnable": False} for _ in range(257)]
        result = summarize_ap_wlan_overrides({"ssidOverrides": rows})
        self.assertEqual(result["entry_count"], 257)
        self.assertEqual(result["included_entry_count"], 256)
        self.assertEqual(result["truncated_entry_count"], 1)
        self.assertTrue(result["partial"])

    def test_rejects_wrong_root_and_oversized_response(self):
        for raw in (None, [], {}, {"ssidOverrides": {}}, {"ssidOverrides": [], **{
                f"extra{i}": i for i in range(8)}}):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(ApWlanOverridesError):
                summarize_ap_wlan_overrides(raw)


class ApWlanOverridesClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref, self.ap_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"
        self.client._device_macs_by_site_ref[self.site_ref] = {
            self.ap_ref: "AA-BB-CC-DD-EE-FF"}

    def test_reads_exact_v2_inventory_bound_route(self):
        path = "/openapi/v2/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/override"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "result": {"ssidOverrides": []}}) as request:
            result = self.client.read_ap_wlan_overrides(self.site_ref, self.ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "ap_wlan_overrides")

    def test_modified_path_and_controller_error_are_rejected(self):
        with patch.object(self.client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET",
                    "/openapi/v2/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/override?raw=1")
        connection.assert_not_called()
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"errorCode": -39303}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_ap_wlan_overrides(self.site_ref, self.ap_ref)


if __name__ == "__main__":
    unittest.main()
