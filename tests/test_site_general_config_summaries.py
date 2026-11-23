import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_gateway_general_config_summary import summarize_gateway_general_config
from app.site_switch_general_config_summary import summarize_switch_general_config


class SiteGeneralConfigSummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-internal"

    def test_gateway_led_modes_and_safe_setting_availability_omit_values(self):
        result = summarize_gateway_general_config({
            "name": "private gateway", "ledSetting": 2, "tagIds": ["private-tag"],
            "location": {"latitude": 1.2, "longitude": 3.4},
            "snmp": {"community": "secret-community"}, "rememberDevice": 7,
        })
        self.assertEqual(result["led"], "site_settings")
        self.assertEqual(result["remember_device"], "present_uninterpreted")
        self.assertEqual(result["snmp"], "present_redacted")
        for secret in ("private gateway", "private-tag", "1.2", "3.4",
                       "secret-community", '"rememberDevice"'):
            self.assertNotIn(secret, repr(result))

    def test_gateway_missing_and_unknown_led_settings_are_distinct(self):
        result = summarize_gateway_general_config({"ledSetting": 9})
        self.assertEqual(result["led"], "unknown")
        self.assertEqual(result["remember_device"], "missing")
        self.assertEqual(result["snmp"], "missing")
        self.assertEqual(result["status"], "partial")

    def test_switch_counts_documented_jumbo_lag_and_led_modes_redacted(self):
        result = summarize_switch_general_config({
            "name": "private switch", "tagIds": ["private-tag"],
            "location": {"latitude": 1, "longitude": 2},
            "snmp": {"community": "private-community"},
            "ledSetting": 0, "jumboFollowSite": False, "jumbo": 9216,
            "lagHashAlgFollowSite": False, "lagHashAlg": 5,
            "sdm": {"templateId": "private-template"},
        })
        self.assertEqual(result["led"], "off")
        self.assertEqual(result["jumbo"], "device_specific_valid")
        self.assertEqual(result["lag_hash"], "device_specific_src_ip_and_dst_ip")
        self.assertEqual(result["sdm"], "present")
        for secret in ("private switch", "private-tag", "private-community",
                       "private-template", '"jumbo"', '"lagHashAlg"'):
            self.assertNotIn(secret, repr(result))

    def test_switch_source_specific_missing_follow_fields_are_not_zero_values(self):
        result = summarize_switch_general_config({
            "ledSetting": 1, "jumbo": 4096, "lagHashAlg": 2,
        })
        self.assertEqual(result["jumbo"], "missing_valid")
        self.assertEqual(result["lag_hash"], "missing_src_mac_and_dst_mac")
        self.assertTrue(result["partial"])

    def test_fresh_gateway_inventory_binding_and_redacted_read(self):
        gateway_ref, mac = "b" * 24, "00:11:22:33:44:55"
        def inventory(site_ref):
            self.client._gateway_macs_by_site_ref[site_ref] = {gateway_ref: mac}
            return {"items": [{"device_ref": gateway_ref, "device_type": "gateway"}]}
        with patch.object(self.client, "list_devices", side_effect=inventory) as devices, \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"ledSetting": 1, "rememberDevice": 6,
                               "snmp": {"community": "private-community"},
                               "name": "private-gateway"},
                }) as request:
            result = self.client.read_site_gateway_general_config_summary(
                self.site_ref, gateway_ref)
        devices.assert_called_once_with(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-internal/gateways/00:11:22:33:44:55/general-config",
            token="token")
        self.assertEqual(result["led"], "on")
        self.assertNotIn(mac, repr(result))
        self.assertNotIn("private-community", repr(result))

    def test_fresh_switch_inventory_binding_and_redacted_read(self):
        switch_ref, mac = "c" * 24, "00:11:22:33:44:66"
        def inventory(site_ref):
            self.client._switch_macs_by_site_ref[site_ref] = {switch_ref: mac}
            return {"items": [{"device_ref": switch_ref, "device_type": "switch"}]}
        with patch.object(self.client, "list_devices", side_effect=inventory) as devices, \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"ledSetting": 2, "jumbo": 1518, "lagHashAlg": 0,
                               "name": "private-switch", "snmp": {"auth": "secret"}},
                }) as request:
            result = self.client.read_site_switch_general_config_summary(
                self.site_ref, switch_ref)
        devices.assert_called_once_with(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-internal/switches/00:11:22:33:44:66/general-config",
            token="token")
        self.assertEqual(result["led"], "site_settings")
        self.assertNotIn(mac, repr(result))
        self.assertNotIn("private-switch", repr(result))
        self.assertNotIn("secret", repr(result))

    def test_ambiguous_inventory_rejects_without_read(self):
        gateway_ref = "b" * 24
        with patch.object(self.client, "list_devices", return_value={
            "items": [{"device_ref": gateway_ref}, {"device_ref": gateway_ref}],
        }), patch.object(self.client, "_request_json") as request:
            with self.assertRaises(OpenApiError) as error:
                self.client.read_site_gateway_general_config_summary(self.site_ref, gateway_ref)
        self.assertEqual(error.exception.code, "gateway_ref_ambiguous")
        request.assert_not_called()

    def test_general_config_request_guards_are_controller_and_path_bound(self):
        self.assertTrue(self.client._gateway_general_config_request_valid(
            "/openapi/v1/ctrl/sites/site-1/gateways/00:11:22:33:44:55/general-config"))
        self.assertFalse(self.client._gateway_general_config_request_valid(
            "/openapi/v1/other/sites/site-1/gateways/00:11:22:33:44:55/general-config"))
        self.assertTrue(self.client._switch_general_config_request_valid(
            "/openapi/v1/ctrl/sites/site-1/switches/00:11:22:33:44:66/general-config"))
        self.assertFalse(self.client._switch_general_config_request_valid(
            "/openapi/v1/ctrl/sites/site-1/switches/00:11:22:33:44:66/general-config?x=1"))


if __name__ == "__main__":
    unittest.main()
