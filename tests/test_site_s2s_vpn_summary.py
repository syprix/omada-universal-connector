import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_s2s_vpn_summary import (
    SiteS2SVpnError, project_s2s_peer_status, project_s2s_vpn_inventory,
)


class SiteS2SVpnSummaryTests(unittest.TestCase):
    def test_inventory_returns_only_opaque_references_and_type_counts(self):
        result = project_s2s_vpn_inventory([
            {"id": "secret-vpn-id", "name": "private-name", "siteVpnType": 0,
             "status": True, "remoteIp": "192.0.2.1"},
            {"id": "another-secret", "name": "private-name-2", "siteVpnType": 1},
        ], ["a" * 24, "b" * 24])
        self.assertEqual(result["vpn_type_counts"],
                         {"auto_ipsec": 1, "manual_ipsec": 1, "unknown": 0})
        self.assertEqual([item["vpn_ref"] for item in result["items"]],
                         ["a" * 24, "b" * 24])
        for secret in ("secret-vpn-id", "private-name", "192.0.2.1"):
            self.assertNotIn(secret, str(result))

    def test_peer_status_counts_use_documented_filter_semantics(self):
        result = project_s2s_peer_status([
            {"status": 1, "name": "secret", "remoteIp": "192.0.2.2"},
            {"status": 0}, {"status": 99}, {},
        ], 4, 1, 10, support_wireguard_status=True)
        self.assertEqual(result["peer_status_counts"],
                         {"connected": 1, "disconnected": 1, "unknown": 2})
        self.assertEqual(result["status_semantics"]["1"], "connected")
        self.assertNotIn("secret", str(result))
        self.assertTrue(result["partial"])
        with self.assertRaises(SiteS2SVpnError):
            project_s2s_peer_status({}, 0, 0, 1)

    def test_selected_vpn_is_refreshed_and_resolved_within_its_site(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=1))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        inventory = {"errorCode": 0, "result": [
            {"id": "vpn-42", "name": "private", "siteVpnType": 0, "status": True}]}
        peers = {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
                  "currentSize": 1, "supportWireguardStatus": True,
                  "data": [{"id": "peer-secret", "vpnId": "vpn-42", "name": "private-peer",
                            "remoteIp": "192.0.2.8", "status": 1}]}}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=[inventory, inventory, peers]) as request:
            selection = client.list_site_s2s_vpn_inventory_summary(site_ref)
            vpn_ref = selection["items"][0]["vpn_ref"]
            result = client.read_site_s2s_peer_status_summary(site_ref, vpn_ref)
        self.assertEqual(result["peer_status_counts"]["connected"], 1)
        self.assertNotIn("peer-secret", str(result))
        self.assertEqual([call.args[1] for call in request.call_args_list], [
            "/openapi/v1/ctrl/sites/site_internal/vpn/site-to-site-vpns",
            "/openapi/v1/ctrl/sites/site_internal/vpn/site-to-site-vpns",
            "/openapi/v1/ctrl/sites/site_internal/setting/vpn/stats/s2s/vpn-42/peer?page=1&pageSize=100",
        ])
        self.assertTrue(client._site_s2s_vpn_inventory_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/vpn/site-to-site-vpns"))
        self.assertTrue(client._site_s2s_peer_status_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/setting/vpn/stats/s2s/vpn-42/peer?page=1&pageSize=100"))
        client._site_ids_by_ref["9" * 24] = "other_site"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=inventory):
            with self.assertRaisesRegex(OpenApiError, "vpn_ref_unknown"):
                client.read_site_s2s_peer_status_summary("9" * 24, vpn_ref)

    def test_duplicate_inventory_ids_are_never_selectable(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        duplicate_inventory = {"errorCode": 0, "result": [
            {"id": "vpn-duplicate", "siteVpnType": 0},
            {"id": "vpn-duplicate", "siteVpnType": 1},
        ]}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=duplicate_inventory):
            result = client.list_site_s2s_vpn_inventory_summary(site_ref)
        self.assertEqual(result["duplicate_id_count"], 2)
        self.assertEqual(result["items"], [])
        self.assertEqual(client._s2s_vpn_ids_by_site_ref[site_ref], {})
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
