from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_ipv6_setting import ApIpv6SettingError, summarize_ap_ipv6_setting


class ApIpv6SettingProjectionTests(unittest.TestCase):
    def test_dynamic_mode_redacts_ipv6_dns_addresses(self):
        result = summarize_ap_ipv6_setting({
            "ipv6Enable": True, "mode": "dynamic",
            "dynamicIpv6Setting": {"dnsMode": 1, "priDns": "2001:db8::53",
                                   "sndDns": "2001:db8::54"},
        })
        self.assertTrue(result["ipv6_enabled"])
        self.assertEqual(result["mode"], "dynamic")
        self.assertEqual(result["dns_mode"], 1)
        self.assertEqual(result["redacted_address_value_count"], 2)
        self.assertFalse(result["partial"])
        self.assertNotIn("2001:db8::53", repr(result))

    def test_static_mode_retains_prefix_length_only(self):
        result = summarize_ap_ipv6_setting({
            "ipv6Enable": True, "mode": "static",
            "staticIpv6Setting": {"ipv6Addr": "2001:db8::15", "prefixLen": 64,
                                  "defaultGate": "2001:db8::1",
                                  "priDns": "2001:db8::53"},
        })
        self.assertEqual(result["static_prefix_length"], 64)
        self.assertEqual(result["redacted_address_value_count"], 3)
        self.assertFalse(result["partial"])
        for private in ("2001:db8::15", "2001:db8::1", "2001:db8::53"):
            self.assertNotIn(private, repr(result))

    def test_disabled_ipv6_and_incomplete_or_unknown_fields(self):
        result = summarize_ap_ipv6_setting({
            "ipv6Enable": False, "dynamicIpv6Setting": {
                "dnsMode": 4, "secret": "private"},
        })
        self.assertFalse(result["ipv6_enabled"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_rejects_invalid_root_shapes(self):
        for value in (None, [], {f"extra{index}": True for index in range(9)}):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ApIpv6SettingError):
                    summarize_ap_ipv6_setting(value)


class ApIpv6SettingClientTests(unittest.TestCase):
    def test_reads_fixed_route_for_inventoried_ap(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        response = {"errorCode": 0, "result": {
            "ipv6Enable": True, "mode": "dynamic",
            "dynamicIpv6Setting": {"dnsMode": 0}}}
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/ipv6-setting"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_ap_ipv6_setting(site_ref, ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "ap_ipv6_setting")

    def test_request_guard_rejects_modified_ipv6_route(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET",
                    "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/ipv6-setting?extra=1")
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
