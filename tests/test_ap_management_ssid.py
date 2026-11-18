from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_management_ssid import ApManagementSsidError, summarize_ap_management_ssid
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ApManagementSsidProjectionTests(unittest.TestCase):
    def test_projects_safe_settings_and_redacts_name_key_and_network_id(self):
        result = summarize_ap_management_ssid({
            "status": True, "name": "private-wlan", "security": 3,
            "broadcast": False,
            "pskSetting": {"securityKey": "private-password", "versionPsk": 2,
                           "encryptionPsk": 3},
            "vlanSetting": {"mode": 1, "customConfig": {
                "customMode": 1, "lanNetworkId": "private-network", "vlanId": 123}},
        })
        self.assertEqual(result["resource"], "ap_management_ssid")
        self.assertTrue(result["enabled"])
        self.assertFalse(result["broadcast_enabled"])
        self.assertEqual(result["security_mode_code"], 3)
        self.assertEqual(result["vlan_mode_code"], 1)
        self.assertEqual(result["custom_vlan_mode_code"], 1)
        self.assertTrue(result["vlan_id_present"])
        self.assertTrue(result["network_binding_present"])
        self.assertEqual(result["redacted_field_count"], 3)
        for value in ("private-wlan", "private-password", "private-network"):
            self.assertNotIn(value, repr(result))
        self.assertFalse(result["partial"])

    def test_enterprise_profile_id_is_redacted(self):
        result = summarize_ap_management_ssid({
            "status": False, "name": "enterprise", "security": 2,
            "broadcast": True, "entSetting": {
                "radiusProfileId": "private-profile", "versionEnt": 1,
                "encryptionEnt": 3}, "vlanSetting": {"mode": 0},
        })
        self.assertTrue(result["enterprise_settings_present"])
        self.assertEqual(result["redacted_field_count"], 2)
        self.assertNotIn("private-profile", repr(result))

    def test_invalid_and_unknown_values_mark_partial(self):
        result = summarize_ap_management_ssid({
            "status": 1, "name": "ok", "security": 99, "broadcast": True,
            "vlanSetting": {"mode": True, "future": "private"},
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_rejects_invalid_root(self):
        for raw in (None, [], {str(i): i for i in range(17)}):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(ApManagementSsidError):
                summarize_ap_management_ssid(raw)


class ApManagementSsidClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref, self.ap_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"
        self.client._device_macs_by_site_ref[self.site_ref] = {
            self.ap_ref: "AA-BB-CC-DD-EE-FF"}

    def test_reads_fixed_inventoried_ap_route(self):
        response = {"errorCode": 0, "result": {
            "status": True, "name": "private", "security": 0,
            "broadcast": True, "vlanSetting": {"mode": 0}}}
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/management-wlan"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=response) as request:
            result = self.client.read_ap_management_ssid(self.site_ref, self.ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "ap_management_ssid")
        self.assertNotIn("private", repr(result))

    def test_rejects_modified_path_and_nonzero_error(self):
        with patch.object(self.client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET",
                    "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/management-wlan?extra=1")
        connection.assert_not_called()
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"errorCode": 1}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_ap_management_ssid(self.site_ref, self.ap_ref)


if __name__ == "__main__":
    unittest.main()
