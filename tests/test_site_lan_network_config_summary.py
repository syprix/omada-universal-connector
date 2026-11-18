from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_lan_network_config_summary import (
    SiteLanNetworkSummaryError, project_site_lan_networks,
)


FEATURES = {
    "isolation": "isolated_network", "allLan": "all_lan_network",
    "igmpSnoopEnable": "igmp_snooping",
    "fastLeaveEnable": "igmp_fast_leave", "mldSnoopEnable": "mld_snooping",
    "dhcpL2RelayEnable": "dhcp_l2_relay", "portal": "portal_enabled",
    "accessControlRule": "access_control_rule_enabled", "rateLimit": "rate_limit_enabled",
    "arpDetectionEnable": "arp_detection_enabled", "qosQueueEnable": "qos_queue_enabled",
    "existMultiVlan": "multi_vlan_configured", "existRA": "router_advertisement_configured",
    "existCustomDhcpOption": "custom_dhcp_options_configured",
    "existDhcpNextServer": "dhcp_next_server_configured",
    "existArpDetection": "arp_detection_configured",
    "existNetworkIsolation": "network_isolation_configured",
    "subnetOverrideEnable": "subnet_override_enabled", "subnetOverride": "subnet_override",
    "primary": "primary_network",
}


def row(purpose=0, value=True):
    return {"id": "private-network-id", "site": "private-site-id",
            "name": "private-network-name", "purpose": purpose,
            "vlan": 27, "gatewaySubnet": "192.0.2.1/24",
            "dhcpSettings": {"server": "private"},
            **{field: value for field in FEATURES}}


def page(number, total, rows):
    return {"totalRows": total, "currentPage": number,
            "currentSize": len(rows), "data": rows}


class SiteLanNetworkProjectionTests(unittest.TestCase):
    def test_aggregates_purpose_and_feature_flags_without_private_values(self):
        one, two = row(0, True), row(1, False)
        result = project_site_lan_networks([page(1, 2, [one, two])])
        self.assertEqual(result["data"]["purpose_code_counts"], {"0": 1, "1": 1})
        self.assertEqual(result["data"]["feature_boolean_counts"]["igmp_snooping"],
                         {"enabled_count": 1, "disabled_count": 1,
                          "unreported_count": 0})
        self.assertFalse(result["partial"])
        for private in ("private-network-id", "private-site-id", "private-network-name",
                        "192.0.2.1/24", "private"):
            self.assertNotIn(private, repr(result))

    def test_unknown_purpose_missing_feature_and_truncation_are_reported(self):
        value = row(7)
        value.pop("igmpSnoopEnable")
        result = project_site_lan_networks([
            page(i, 700, [value] * 100) for i in range(1, 6)])
        self.assertEqual(result["data"]["unknown_purpose_code_count"], 500)
        self.assertTrue(result["data"]["truncated"])
        self.assertIsNone(result["data"]["purpose_code_counts"])
        self.assertEqual(result["data"]["feature_boolean_counts"]["igmp_snooping"][
            "unreported_count"], 500)
        self.assertTrue(result["partial"])
        with self.assertRaises(SiteLanNetworkSummaryError):
            project_site_lan_networks([page(i, 0, []) for i in range(6)])


class SiteLanNetworkClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_bounded_v3_pages(self):
        responses = [{"result": page(i, 300, [row(0)] * 100)} for i in range(1, 4)]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=responses) as request:
            result = self.client.read_site_lan_network_config_summary(self.site_ref)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(request.call_args_list[0].args[1],
                         "/openapi/v3/ctrl/sites/site_internal/lan-networks?page=1&pageSize=100")
        self.assertEqual(request.call_args_list[-1].args[1],
                         "/openapi/v3/ctrl/sites/site_internal/lan-networks?page=3&pageSize=100")
        self.assertEqual(result["data"]["returned_network_count"], 300)

    def test_path_guard_and_unknown_site(self):
        path = "/openapi/v3/ctrl/sites/site_internal/lan-networks?page=1&pageSize=100"
        self.assertTrue(self.client._site_lan_networks_v3_request_valid(path))
        self.assertFalse(self.client._site_lan_networks_v3_request_valid(
            path.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_lan_networks_v3_request_valid(
            path + "&sorts.name=asc"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_lan_network_config_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
