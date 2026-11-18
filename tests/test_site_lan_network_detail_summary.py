import unittest
from unittest.mock import patch

from app.site_lan_network_detail_summary import project_site_lan_network_detail
from app.openapi import OpenApiConfig, OmadaOpenApiClient


class SiteLanNetworkDetailSummaryTests(unittest.TestCase):
    def test_projects_diagnostics_and_redacts_identifiers_dns_and_ranges(self):
        value = {"id": "internal-id", "site": "internal-site", "name": "private-name",
                 "purpose": 1, "deviceType": 1, "application": 0, "vlanType": 0,
                 "vlan": 20, "gatewaySubnet": "192.168.20.1/24", "isolation": True,
                 "igmpSnoopEnable": True, "mldSnoopEnable": False,
                 "dhcpSettings": {"enable": True, "ipRangePool": [
                     {"ipaddrStart": "192.168.20.10", "ipaddrEnd": "192.168.20.100"}],
                     "priDns": "192.168.20.2"},
                 "deviceMac": "AA-BB-CC-DD-EE-FF"}
        result = project_site_lan_network_detail(value)
        data = result["data"]
        self.assertEqual(data["purpose_label"], "interface")
        self.assertEqual(data["gateway_subnet"], "192.168.20.1/24")
        self.assertEqual(data["dhcp"], {"enabled": True, "pool_range_count": 1})
        self.assertFalse(result["partial"])
        self.assertGreater(data["redacted_field_count"], 0)
        for secret in ("internal-id", "internal-site", "private-name", "192.168.20.10", "192.168.20.2", "AA-BB-CC-DD-EE-FF"):
            self.assertNotIn(secret, repr(result))

    def test_client_resolves_network_ref_in_site_and_uses_fixed_get(self):
        client = OmadaOpenApiClient(OpenApiConfig("https://controller.example", "ctrl", "id", "secret",
                                                   cert_sha256="a" * 64))
        site_ref, net_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        client._network_ids_by_site_ref[site_ref] = {net_ref: "network_1"}
        result_body = {"purpose": 0, "deviceType": 1, "igmpSnoopEnable": True,
                       "name": "private", "vlan": 20, "isolation": False}
        with patch.object(client, "_access_token", return_value="token"), patch.object(
                client, "_request_json", return_value={"result": result_body}) as request:
            result = client.read_site_lan_network_detail_summary(site_ref, net_ref)
        request.assert_called_once_with("GET", "/openapi/v1/ctrl/sites/site_1/lan-networks/network_1", token="token")
        self.assertEqual(result["resource"], "site_lan_network_detail_summary")
        self.assertNotIn("private", repr(result))

    def test_invalid_subnet_and_unknown_codes_mark_partial(self):
        result = project_site_lan_network_detail({"purpose": 9, "deviceType": 12,
                                                  "name": "x", "igmpSnoopEnable": True,
                                                  "gatewaySubnet": "not-an-ip"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["invalid_field_count"], 3)

    def test_er7212pc_optional_fields_and_disabled_dhcp_are_valid(self):
        result = project_site_lan_network_detail({
            "purpose": 0, "igmpSnoopEnable": False,
            "dhcpSettings": {"enable": False},
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["dhcp"], {"enabled": False})


if __name__ == "__main__":
    unittest.main()
