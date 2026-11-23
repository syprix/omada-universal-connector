import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_vpn_client_config_summary import summarize_vpn_client_config_rows


class SiteVpnClientConfigSummaryTests(unittest.TestCase):
    def test_counts_only_documented_protocols_and_redacts_identity_values(self):
        result = summarize_vpn_client_config_rows([
            {"id": "private-id", "name": "private-name", "vpnType": 0,
             "status": True, "wans": ["private-wan"]},
            {"vpnType": 4, "status": False},
            {"vpnType": 99, "status": None},
        ])
        self.assertEqual(result["by_documented_protocol"],
                         {"l2tp": 1, "wireguard": 1, "unknown": 1})
        self.assertEqual(result["by_reported_configuration_flag"],
                         {"true": 1, "false": 1, "unreported": 1})
        self.assertTrue(result["partial"])
        self.assertIn("not tunnel connectivity", result["configuration_flag_semantics"])
        for private in ("private-id", "private-name", "private-wan"):
            self.assertNotIn(private, repr(result))

    def test_unknown_fields_and_omitted_rows_mark_partial_without_echoing_values(self):
        result = summarize_vpn_client_config_rows([
            {"vpnType": 1, "status": True, "futureField": "private-secret-value"}, {}],
            omitted_rows=3)
        self.assertEqual(result["omitted_client_count"], 3)
        self.assertEqual(result["reported_client_total"], 5)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["by_reported_configuration_flag"]["unreported"], 1)
        self.assertNotIn("private-secret-value", repr(result))
        self.assertTrue(result["partial"])

    def test_client_paginates_only_page_and_page_size_and_binds_site(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site-internal"
        first = {"totalRows": 101, "currentPage": 1, "currentSize": 100,
                 "data": [{"vpnType": 3, "status": True} for _ in range(100)]}
        second = {"totalRows": 101, "currentPage": 2, "currentSize": 1,
                  "data": [{"vpnType": 4, "status": False}]}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=[
                    {"errorCode": 0, "result": first},
                    {"errorCode": 0, "result": second},
                ]) as request:
            result = client.read_site_vpn_client_config_summary(site_ref)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[1],
                         "/openapi/v2/ctrl/sites/site-internal/vpn/client-to-site-vpn-clients?page=1&pageSize=100")
        self.assertEqual(request.call_args_list[1].args[1],
                         "/openapi/v2/ctrl/sites/site-internal/vpn/client-to-site-vpn-clients?page=2&pageSize=100")
        self.assertEqual(result["reported_client_total"], 101)
        self.assertEqual(result["by_documented_protocol"], {"openvpn": 100, "wireguard": 1})
        self.assertTrue(client._site_vpn_client_config_v2_request_valid(
            "/openapi/v2/ctrl/sites/site-internal/vpn/client-to-site-vpn-clients?page=10&pageSize=100"))
        self.assertFalse(client._site_vpn_client_config_v2_request_valid(
            "/openapi/v2/ctrl/sites/site-internal/vpn/client-to-site-vpn-clients?page=11&pageSize=100"))
        self.assertFalse(client._site_vpn_client_config_v2_request_valid(
            "/openapi/v2/other/sites/site-internal/vpn/client-to-site-vpn-clients?page=1&pageSize=100"))

    def test_rejects_oversized_projection(self):
        with self.assertRaises(ValueError):
            summarize_vpn_client_config_rows([{}] * 1001)


if __name__ == "__main__":
    unittest.main()
