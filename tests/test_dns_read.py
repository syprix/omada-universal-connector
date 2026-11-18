from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class DnsReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_dns_cache_settings_typed(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"enable": True, "ttl": 3600}}):
            result = self.client.read_dns_cache_settings(self.site_ref)
        self.assertEqual(result["data"], {"enabled": True, "ttl_seconds": 3600})
        self.assertEqual(next(x for x in self.client.capabilities()["items"]
                              if x["operation"] == "dns_cache_settings")["runtime_evidence"][0]["result"],
                         "success")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"ttl": 86401}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_dns_cache_settings(self.site_ref)

    def test_dns_proxy_exposes_mode_flags_only(self) -> None:
        payload = {"result": {"enable": True, "type": 1, "supportDnsOverride": True,
                               "existDnsOverride": False,
                               "dohSetting": {"defaultServers": [0, 1], "customizedServers": [
                                   {"server": "https://private.example/dns", "enable": True}]},
                               "dnsOverrideSetting": {"primaryDnsServer": "192.0.2.1",
                                                      "applyNetwork": ["private-network-id"]}}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload):
            result = self.client.read_dns_proxy_settings(self.site_ref)
        self.assertEqual(result["data"], {"enabled": True, "mode": "doh",
            "supports_dns_override": True, "dns_override_configured": False})
        for forbidden in ("private.example", "192.0.2.1", "private-network-id", "customizedServers"):
            self.assertNotIn(forbidden, str(result))

    def test_lan_dns_records_use_opaque_refs_and_hide_all_record_values(self) -> None:
        rows = [{"id": "dns-record-id", "name": "private-record-name",
                 "domain": "private.example", "enable": True, "type": 0,
                 "ipAddresses": ["192.0.2.1"], "ipv6Addresses": ["2001:db8::1"],
                 "aliases": ["private"], "lanNetworkIds": ["network-secret"],
                 "customTtl": True, "ttl": 1200, "dnsServers": ["192.0.2.53"]}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows) as read:
            result = self.client.list_lan_dns_records(self.site_ref)
        read.assert_called_once_with("/openapi/v1/ctrl/sites/site_1/setting/lan/dns", "token")
        self.assertEqual(result["items"], [{"record_ref": result["items"][0]["record_ref"],
            "record_type": "ip", "enabled": True, "custom_ttl": True,
            "ttl_seconds": 1200, "network_count": 1}])
        self.assertEqual(len(result["items"][0]["record_ref"]), 24)
        for forbidden in ("dns-record-id", "private-record-name", "private.example", "192.0.2.1",
                          "2001:db8::1", "network-secret", "192.0.2.53"):
            self.assertNotIn(forbidden, str(result))

    def test_bad_record_and_unknown_site_rejected(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.list_lan_dns_records("b" * 24)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=[{
                    "name": "name", "domain": "domain", "enable": True, "type": 7}]):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.list_lan_dns_records(self.site_ref)

    def test_only_exact_documented_get_paths_are_allowed(self) -> None:
        paths = [
            "/openapi/v1/ctrl/sites/site_1/setting/service/dns-cache",
            "/openapi/v1/ctrl/sites/site_1/setting/service/dns-proxy",
            "/openapi/v1/ctrl/sites/site_1/setting/lan/dns?page=1&pageSize=100",
        ]
        for path in paths:
            with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
                with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                    self.client._request_json("GET", path)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("POST", path)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", paths[2] + "&searchKey=domain")


if __name__ == "__main__":
    unittest.main()
