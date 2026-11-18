from __future__ import annotations

import unittest
from unittest.mock import call, patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_vpn_session_summary import (
    SiteVpnSessionError, project_site_vpn_sessions,
)


def page(number: int, total: int, rows: list[dict[str, object]]) -> dict[str, object]:
    return {"totalRows": total, "currentPage": number,
            "currentSize": len(rows), "data": rows}


def session(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "vpnId": 1, "vpnName": "private-vpn", "userId": 2,
        "userName": "private-user", "interfaceName": "private-iface",
        "serverType": 3, "vpnType": 4, "clientMode": "private-mode",
        "localIp": "10.0.0.2", "remoteIp": "203.0.113.7",
        "downPkts": 10, "downBytes": 1000, "upPkts": 20, "upBytes": 2000,
        "uptime": "private-uptime", "dns": "private-dns",
    }
    row.update(overrides)
    return row


class SiteVpnSessionProjectionTests(unittest.TestCase):
    def test_aggregates_traffic_and_codes_without_identity_values(self) -> None:
        result = project_site_vpn_sessions([page(1, 2, [session(), session(vpnType=5)])])
        self.assertEqual(result["data"]["reported_session_count"], 2)
        self.assertEqual(result["data"]["vpn_type_code_counts"], {"4": 1, "5": 1})
        self.assertEqual(result["data"]["server_type_code_counts"], {"3": 2})
        self.assertEqual(result["data"]["downstream_bytes"], 2000)
        self.assertEqual(result["data"]["upstream_packets"], 40)
        self.assertFalse(result["partial"])
        for secret in ("private-vpn", "private-user", "private-iface", "10.0.0.2",
                       "203.0.113.7", "private-mode", "private-uptime", "private-dns"):
            self.assertNotIn(secret, repr(result))

    def test_missing_counters_are_not_invented_as_zero(self) -> None:
        result = project_site_vpn_sessions([page(1, 1, [session(upBytes=None)])])
        self.assertIsNone(result["data"]["upstream_bytes"])
        self.assertTrue(result["partial"])
        self.assertGreater(result["invalid_field_count"], 0)

    def test_marks_truncation_and_unknown_fields(self) -> None:
        result = project_site_vpn_sessions([page(1, 501, [session(extra="private")])])
        self.assertTrue(result["data"]["truncated"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_rejects_unbounded_outer_shape(self) -> None:
        for value in (None, [], [page(i, 0, []) for i in range(6)]):
            with self.subTest(shape=type(value).__name__), self.assertRaises(SiteVpnSessionError):
                project_site_vpn_sessions(value)


class SiteVpnSessionClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_pages_and_projects_summary(self) -> None:
        responses = [{"result": page(1, 101, [session()] * 100)},
                     {"result": page(2, 101, [session()])}]
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", side_effect=responses) as request:
            result = self.client.read_site_vpn_session_summary(self.site_ref)
        self.assertEqual(request.call_args_list, [
            call("GET", "/openapi/v1/ctrl/sites/site_internal/setting/vpn/stats/tunnel?page=1&pageSize=100", token="test-token"),
            call("GET", "/openapi/v1/ctrl/sites/site_internal/setting/vpn/stats/tunnel?page=2&pageSize=100", token="test-token"),
        ])
        self.assertEqual(result["data"]["returned_session_count"], 101)
        self.assertFalse(result["partial"])

    def test_path_guard_and_unknown_site(self) -> None:
        self.assertTrue(self.client._site_vpn_session_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/setting/vpn/stats/tunnel?page=5&pageSize=100"))
        self.assertFalse(self.client._site_vpn_session_request_valid(
            "/openapi/v1/other/sites/site_internal/setting/vpn/stats/tunnel?page=1&pageSize=100"))
        self.assertFalse(self.client._site_vpn_session_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/setting/vpn/stats/tunnel?page=6&pageSize=100"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_vpn_session_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
