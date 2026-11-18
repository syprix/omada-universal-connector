from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF, GATEWAY_REF = "a" * 24, "d" * 24
GATEWAY_MAC = "00:11:22:33:44:77"


class GatewayDhcpReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._gateway_macs_by_site_ref[SITE_REF] = {GATEWAY_REF: GATEWAY_MAC}

    def test_reads_pages_and_returns_identifier_free_lease_categories(self) -> None:
        page = {"result": {"totalRows": 1, "currentPage": 1, "currentSize": 100,
                            "data": [{"type": 1, "status": 0,
                                      "macAddress": GATEWAY_MAC, "ipAddress": "192.0.2.8",
                                      "name": "private-device", "netId": "network-private",
                                      "netName": "private-lan", "leftLeaseTime": "20 mins"}],
                            "netNameToIdMap": {"private-lan": "network-private"}}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=page) as request:
            result = self.client.list_gateway_dhcp_leases(SITE_REF, GATEWAY_REF)
        request.assert_called_once_with(
            "GET", f"/openapi/v1/ctrl/sites/site_1/gateways/{GATEWAY_MAC}/dhcp/user-list"
            "?page=1&pageSize=100", token="token")
        self.assertEqual(result["summary"], {"total": 1, "devices": 0, "clients": 1,
                                             "dynamic": 1, "static": 0})
        self.assertEqual(result["resource"], "gateway_dhcp_leases")
        self.assertEqual(result["site_ref"], SITE_REF)
        self.assertEqual(result["device_ref"], GATEWAY_REF)
        for private in (GATEWAY_MAC, "192.0.2.8", "private-device", "private-lan",
                        "network-private", "20 mins"):
            self.assertNotIn(private, repr(result))

    def test_unknown_gateway_is_rejected_without_a_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "gateway_ref_unknown"):
                self.client.list_gateway_dhcp_leases(SITE_REF, "e" * 24)
        request.assert_not_called()

    def test_paged_route_allows_only_the_documented_query(self) -> None:
        route = (f"/openapi/v1/ctrl/sites/site_1/gateways/{GATEWAY_MAC}/dhcp/user-list"
                 "?page=1&pageSize=100")
        with patch.object(self.client, "_connection", side_effect=OpenApiError("reached")):
            with self.assertRaisesRegex(OpenApiError, "reached"):
                self.client._request_json("GET", route)
        for unsafe in (route + "&searchKey=private", route.replace("page=1", "page=-1")):
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", unsafe)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("POST", route)


if __name__ == "__main__":
    unittest.main()
