import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_vpn_server_config_summary import summarize_vpn_server_config_rows


class SiteVpnServerConfigSummaryTests(unittest.TestCase):
    def test_counts_documented_protocol_and_status_flag_redacting_secrets(self):
        result = summarize_vpn_server_config_rows([
            {"id": "private-id", "name": "private-name", "vpnType": 2,
             "status": True, "wans": ["private-wan"], "userCount": 7},
            {"vpnType": 5, "status": False},
            {"vpnType": 99, "status": None},
        ])
        self.assertEqual(result["by_documented_protocol"],
                         {"ipsec": 1, "ssl_vpn": 1, "unknown": 1})
        self.assertEqual(result["by_reported_activation_flag"],
                         {"enabled": 1, "disabled": 1, "unreported": 1})
        self.assertTrue(result["partial"])
        self.assertIn("not tunnel connectivity", result["activation_semantics"])
        for private in ("private-id", "private-name", "private-wan"):
            self.assertNotIn(private, repr(result))

    def test_unknown_fields_omissions_and_invalid_values_mark_partial(self):
        result = summarize_vpn_server_config_rows([
            {"vpnType": 0, "status": True, "futureField": "private-secret-value"}, {}],
            omitted_rows=3)
        self.assertEqual(result["omitted_server_count"], 3)
        self.assertEqual(result["reported_server_total"], 5)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["by_reported_activation_flag"]["unreported"], 1)
        self.assertNotIn("private-secret-value", repr(result))
        self.assertTrue(result["partial"])

    def test_client_paginates_bounded_v2_endpoint_and_binds_site(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site-internal"
        first = {"totalRows": 101, "currentPage": 1, "currentSize": 100,
                 "data": [{"vpnType": 2, "status": True} for _ in range(100)]}
        second = {"totalRows": 101, "currentPage": 2, "currentSize": 1,
                  "data": [{"vpnType": 5, "status": False}]}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=[
                    {"errorCode": 0, "result": first},
                    {"errorCode": 0, "result": second},
                ]) as request:
            result = client.read_site_vpn_server_config_summary(site_ref)
        self.assertEqual(request.call_count, 2)
        self.assertIn("/openapi/v2/ctrl/sites/site-internal/vpn/client-to-site-vpn-servers?page=1&pageSize=100",
                      request.call_args_list[0].args[1])
        self.assertIn("?page=2&pageSize=100", request.call_args_list[1].args[1])
        self.assertEqual(result["reported_server_total"], 101)
        self.assertEqual(result["by_documented_protocol"]["ssl_vpn"], 1)
        self.assertTrue(client._site_vpn_server_config_v2_request_valid(
            "/openapi/v2/ctrl/sites/site-internal/vpn/client-to-site-vpn-servers?page=10&pageSize=100"))
        self.assertFalse(client._site_vpn_server_config_v2_request_valid(
            "/openapi/v2/ctrl/sites/site-internal/vpn/client-to-site-vpn-servers?page=11&pageSize=100"))
        self.assertFalse(client._site_vpn_server_config_v2_request_valid(
            "/openapi/v2/other/sites/site-internal/vpn/client-to-site-vpn-servers?page=1&pageSize=100"))

    def test_rejects_oversized_projection(self):
        with self.assertRaises(ValueError):
            summarize_vpn_server_config_rows([{}] * 1001)


if __name__ == "__main__":
    unittest.main()
