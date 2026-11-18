from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class DhcpReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_summarizes_dhcp_user_bindings_without_identifiers(self) -> None:
        rows = [
            {"type": 0, "ipAddress": "192.0.2.1", "macAddress": "00:11:22:33:44:55",
             "name": "private-host", "netId": "net-1", "netName": "private-network",
             "serverName": "private-router", "serverMac": "00:11:22:33:44:66",
             "leftLeaseTime": "12 hours", "status": 0},
            {"type": 1, "ipAddress": "192.0.2.2", "macAddress": "00:11:22:33:44:77",
             "name": "private-client", "netId": "net-2", "netName": "private-network",
             "leftLeaseTime": "forever", "status": 1},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows) as read:
            result = self.client.list_dhcp_leases(self.site_ref)
        read.assert_called_once_with("/openapi/v1/ctrl/sites/site_1/setting/service/dhcp/user-list", "token")
        self.assertEqual(result["summary"], {"total": 2, "devices": 1, "clients": 1,
                                           "dynamic": 1, "static": 1})
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual({row["entity_type"] for row in result["items"]}, {"device", "client"})
        self.assertEqual({row["binding_status"] for row in result["items"]}, {"dynamic", "static"})
        self.assertTrue(all(len(row["lease_ref"]) == 24 for row in result["items"]))
        for forbidden in ("192.0.2.", "00:11:22:33:44", "private", "net-1", "12 hours", "forever"):
            self.assertNotIn(forbidden, str(result))
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "dhcp_leases")["runtime_evidence"]
        self.assertEqual(evidence[0]["result"], "success")

    def test_unknown_site_and_invalid_record_rejected(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.list_dhcp_leases("b" * 24)
        for bad in ({"type": 3, "status": 0, "macAddress": "00:11:22:33:44:55"},
                    {"type": 0, "status": True, "macAddress": "00:11:22:33:44:55"},
                    {"type": 0, "status": 0, "macAddress": "private"}):
            with patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_read_pages", return_value=[bad]):
                with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                    self.client.list_dhcp_leases(self.site_ref)

    def test_exact_paged_get_allowlist(self) -> None:
        path = "/openapi/v1/ctrl/sites/site_1/setting/service/dhcp/user-list?page=1&pageSize=100"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", path + "&searchKey=private")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("POST", path)


if __name__ == "__main__":
    unittest.main()
