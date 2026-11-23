import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_s2s_vpn_v2_summary import summarize_site_s2s_vpn_v2


class SiteS2SVpnV2SummaryTests(unittest.TestCase):
    @staticmethod
    def page(current: int, total: int, rows: list[object], size: int) -> dict[str, object]:
        return {
            "totalRows": total, "currentPage": current, "currentSize": size, "data": rows,
            "supportIPsec": True, "supportAutoWireGuard": True,
            "supportManualWgLocalNetwork": False, "supportIPsecFailover": True,
        }

    def test_projects_documented_configuration_counts_and_redacts_values(self) -> None:
        result = summarize_site_s2s_vpn_v2([self.page(1, 2, [
            {"id": "private-vpn-id", "name": "private vpn", "status": True,
             "vpnType": 2, "siteVpnType": 1, "wans": ["private-wan-id"],
             "failoverSetting": {"backupWan": "private-backup-wan", "status": True},
             "networkType": 1, "networkList": [],
             "customNetwork": [{"ip": "192.0.2.0", "mask": 24,
                                 "description": "private network"}],
             "activeClients": 4},
            {"id": "private-vpn-id-2", "name": "private vpn 2", "status": False,
             "vpnType": 4, "siteVpnType": 0, "wans": [], "failoverSetting": {},
             "networkType": 0, "networkList": ["private-network-id"],
             "customNetwork": []},
        ], 2)])
        self.assertEqual(result["reported_vpn_count"], 2)
        self.assertEqual(result["vpn_type_counts"]["ipsec"], 1)
        self.assertEqual(result["vpn_type_counts"]["wireguard"], 1)
        self.assertEqual(result["site_vpn_type_counts"],
                         {"auto": 1, "manual": 1, "unknown": 0})
        self.assertEqual(result["reported_status_flag_counts"],
                         {"true": 1, "false": 1, "unreported": 0})
        self.assertEqual(result["custom_network_entry_count"], 1)
        self.assertEqual(result["network_list_entry_count"], 1)
        self.assertEqual(result["wan_assignment_entry_count"], 1)
        self.assertEqual(result["capability_support_flags"], {
            "ipsec": True, "auto_wireguard": True,
            "manual_wireguard_local_network": False, "ipsec_failover": True,
        })
        self.assertFalse(result["partial"])
        for secret in ("private-vpn-id", "private vpn", "private-wan-id",
                       "private-backup-wan", "192.0.2.0", "private network",
                       "private-network-id"):
            self.assertNotIn(secret, repr(result))

    def test_missing_fields_unknown_codes_and_truncation_are_reported(self) -> None:
        page = {"totalRows": 2, "currentPage": 1, "currentSize": 1,
                "data": [{"status": "up", "vpnType": 8}],
                "supportIPsec": True}
        result = summarize_site_s2s_vpn_v2([page])
        self.assertTrue(result["partial"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["vpn_type_counts"]["unknown"], 1)
        self.assertEqual(result["reported_status_flag_counts"]["unreported"], 1)
        self.assertIsNone(result["capability_support_flags"]["ipsec_failover"])

    def test_client_paginates_v2_path_and_validates_controller_binding(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site-internal"
        support = {"supportIPsec": True, "supportAutoWireGuard": True,
                   "supportManualWgLocalNetwork": True, "supportIPsecFailover": True}
        first = {"totalRows": 101, "currentPage": 1, "currentSize": 100,
                 "data": [{"vpnType": 2, "siteVpnType": 0, "status": True,
                           "wans": [], "networkList": [], "customNetwork": [],
                           "failoverSetting": {}} for _ in range(100)], **support}
        second = {"totalRows": 101, "currentPage": 2, "currentSize": 1,
                  "data": [{"vpnType": 4, "siteVpnType": 1, "status": False,
                            "wans": [], "networkList": [], "customNetwork": [],
                            "failoverSetting": {}}], **support}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=[
                    {"errorCode": 0, "result": first},
                    {"errorCode": 0, "result": second},
                ]) as request:
            result = client.read_site_s2s_vpn_v2_summary(site_ref)
        self.assertEqual(request.call_count, 2)
        self.assertIn("/openapi/v2/ctrl/sites/site-internal/vpn/site-to-site-vpns?page=1&pageSize=100",
                      request.call_args_list[0].args[1])
        self.assertIn("?page=2&pageSize=100", request.call_args_list[1].args[1])
        self.assertEqual(result["returned_vpn_count"], 101)
        self.assertEqual(result["vpn_type_counts"]["wireguard"], 1)
        self.assertTrue(client._site_s2s_vpn_v2_request_valid(
            "/openapi/v2/ctrl/sites/site-internal/vpn/site-to-site-vpns?page=10&pageSize=100"))
        self.assertFalse(client._site_s2s_vpn_v2_request_valid(
            "/openapi/v2/ctrl/sites/site-internal/vpn/site-to-site-vpns?page=11&pageSize=100"))
        self.assertFalse(client._site_s2s_vpn_v2_request_valid(
            "/openapi/v2/wrong/sites/site-internal/vpn/site-to-site-vpns?page=1&pageSize=100"))


if __name__ == "__main__":
    unittest.main()
