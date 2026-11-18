from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_vlan_ssid_usage_summary import (
    VlanSsidUsageError, project_site_vlan_ssid_usage_summary,
)

SITE_REF = "a" * 24
NETWORK_REF = "b" * 24


def _grid(rows: list[dict[str, object]], total: int | None = None) -> dict[str, object]:
    return {"totalRows": len(rows) if total is None else total,
            "currentPage": 1, "currentSize": 100, "data": rows}


class VlanSsidUsageProjectionTests(unittest.TestCase):
    def test_counts_ssids_and_distinct_groups_without_identity_values(self) -> None:
        result = project_site_vlan_ssid_usage_summary(_grid([
            {"id": "private-ssid-id", "name": "private-name", "wlanId": "group-a",
             "wlanName": "private-group"},
            {"id": "private-ssid-id-2", "name": "other", "wlanId": "group-a"},
            {"wlanId": "group-b"},
        ]))
        self.assertEqual(result["ssid_count"], 3)
        self.assertEqual(result["wlan_group_count"], 2)
        self.assertFalse(result["partial"])
        for secret in ("private-ssid-id", "private-name", "private-group", "group-a", "group-b"):
            self.assertNotIn(secret, repr(result))

    def test_missing_invalid_and_unknown_fields_are_counted(self) -> None:
        result = project_site_vlan_ssid_usage_summary(_grid([
            {"id": "redacted"}, {"wlanId": "bad\nvalue", "unknown": "hidden"},
        ]))
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["redacted_field_count"], 1)
        self.assertNotIn("hidden", repr(result))

    def test_malformed_grids_fail_closed(self) -> None:
        for raw in (None, [], {"totalRows": -1, "data": []},
                    {"totalRows": 2, "data": []}, {"totalRows": 10001, "data": []},
                    {"totalRows": 1, "data": [None]}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(VlanSsidUsageError):
                project_site_vlan_ssid_usage_summary(raw)


class VlanSsidUsageClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site-1"
        self.client._network_ids_by_site_ref[SITE_REF] = {NETWORK_REF: "network-1"}

    def test_reads_site_bound_network_and_fixed_paging(self) -> None:
        raw = {"result": _grid([{"id": "hidden", "name": "secret", "wlanId": "wlan-1"}])}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=raw) as request:
            result = self.client.read_site_vlan_ssid_usage_summary(SITE_REF, NETWORK_REF, 52)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-1/networks/network-1/vlan/52/ssids?page=1&pageSize=100",
            token="token")
        self.assertEqual(result["ssid_count"], 1)
        self.assertNotIn("secret", repr(result))

    def test_invalid_vlan_and_unknown_network_stop_before_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            for vlan in (0, 4095, True, "52"):
                with self.assertRaisesRegex(OpenApiError, "vlan_id_invalid"):
                    self.client.read_site_vlan_ssid_usage_summary(SITE_REF, NETWORK_REF, vlan)
            with self.assertRaisesRegex(OpenApiError, "network_ref_unknown"):
                self.client.read_site_vlan_ssid_usage_summary(SITE_REF, "c" * 24, 52)
        request.assert_not_called()

    def test_unsafe_paths_and_page_values_fail_allowlist(self) -> None:
        good = "/openapi/v1/ctrl/sites/site-1/networks/network-1/vlan/52/ssids?page=1&pageSize=100"
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good + "&sort=private")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("vlan/52", "vlan/0"))
