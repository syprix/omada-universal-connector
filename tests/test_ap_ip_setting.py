from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_ip_setting import ApIpSettingError, summarize_ap_ip_setting


class ApIpSettingProjectionTests(unittest.TestCase):
    def test_dhcp_mode_returns_flags_without_addresses_or_ids(self):
        result = summarize_ap_ip_setting({
            "mode": "DHCP",
            "dhcpIpSetting": {
                "fallback": True, "fallbackIp": "192.0.2.3",
                "fallbackMask": "255.255.255.0", "fallbackGate": "192.0.2.1",
                "useFixedAddr": False, "netId": "private-network-id",
                "dhcpIp": "192.0.2.55", "serverType": "private-server-type",
                "serverMac": "AA:BB:CC:DD:EE:FF", "serverStackId": "private-stack",
            },
            "staticIpSetting": {},
        })
        self.assertEqual(result["mode"], "DHCP")
        self.assertTrue(result["fallback_enabled"])
        self.assertFalse(result["reserved_address_enabled"])
        self.assertEqual(result["redacted_value_count"], 8)
        self.assertFalse(result["partial"])
        for private in ("192.0.2.3", "192.0.2.55", "private-network-id",
                        "private-server-type", "AA:BB:CC:DD:EE:FF", "private-stack"):
            self.assertNotIn(private, repr(result))

    def test_static_mode_redacts_address_and_dns_values(self):
        result = summarize_ap_ip_setting({
            "mode": "Static",
            "staticIpSetting": {"configIp": "203.0.113.7",
                                "configMask": "255.255.255.0",
                                "configGate": "203.0.113.1",
                                "preferredDNS": "203.0.113.53",
                                "alternateDNS": "203.0.113.54"},
        })
        self.assertEqual(result["mode"], "Static")
        self.assertTrue(result["static_setting_present"])
        self.assertEqual(result["redacted_value_count"], 5)
        self.assertFalse(result["partial"])
        for private in ("203.0.113.7", "203.0.113.1", "203.0.113.53"):
            self.assertNotIn(private, repr(result))

    def test_malformed_and_unknown_fields_mark_partial(self):
        result = summarize_ap_ip_setting({
            "mode": "DHCP", "dhcpIpSetting": {
                "fallback": "yes", "fallbackIp": 7, "vendorField": "private"},
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_rejects_invalid_root_shapes(self):
        for value in (None, [], {f"extra{index}": True for index in range(9)}):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ApIpSettingError):
                    summarize_ap_ip_setting(value)


class ApIpSettingClientTests(unittest.TestCase):
    def test_reads_fixed_route_for_inventoried_ap(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        response = {"errorCode": 0, "result": {
            "mode": "DHCP", "dhcpIpSetting": {"fallback": True,
            "fallbackIp": "192.0.2.10"}}}
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/ip-setting"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_ap_ip_setting(site_ref, ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "ap_ip_setting")
        self.assertNotIn("192.0.2.10", repr(result))

    def test_request_guard_rejects_modified_ip_setting_route(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET",
                    "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/ip-setting?extra=1")
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
