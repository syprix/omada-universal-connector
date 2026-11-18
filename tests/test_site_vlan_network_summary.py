from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_vlan_network_summary import (
    SiteVlanNetworkError, project_site_vlan_networks,
)


def page(number: int, total: int, rows: list[dict[str, object]]) -> dict[str, object]:
    return {"totalRows": total, "currentPage": number,
            "currentSize": len(rows), "data": rows}


class SiteVlanNetworkProjectionTests(unittest.TestCase):
    def test_summarizes_purpose_and_vlan_counts_without_identifiers(self) -> None:
        projected = project_site_vlan_networks([page(1, 2, [
            {"purpose": "0", "name": "private name", "id": "private-id", "vlan": 20},
            {"purpose": "1", "name": "another private name", "id": "another-id", "vlan": 30},
        ])])
        self.assertEqual(projected["data"]["reported_total_row_count"], 2)
        self.assertEqual(projected["data"]["returned_row_count"], 2)
        self.assertEqual(projected["data"]["distinct_vlan_id_count"], 2)
        self.assertEqual(projected["data"]["purpose_code_counts"], {"0": 1, "1": 1})
        self.assertFalse(projected["partial"])
        for value in ("private name", "private-id", "another-id", "20", "30"):
            self.assertNotIn(value, repr(projected))

    def test_marks_missing_metadata_and_truncated_cap(self) -> None:
        incomplete = project_site_vlan_networks([{"data": [{"purpose": "0"}]}])
        self.assertTrue(incomplete["partial"])
        self.assertTrue(incomplete["data"]["truncated"])
        pages = [page(i, 600, [{"purpose": "0", "vlan": j} for j in range(100)])
                 for i in range(1, 6)]
        capped = project_site_vlan_networks(pages)
        self.assertEqual(capped["data"]["returned_row_count"], 500)
        self.assertTrue(capped["data"]["truncated"])
        self.assertTrue(capped["partial"])

    def test_counts_invalid_and_unknown_fields_without_returning_them(self) -> None:
        projected = project_site_vlan_networks([page(1, 1, [
            {"purpose": "0", "vlan": True, "internal": "private"},
        ])])
        self.assertEqual(projected["invalid_field_count"], 1)
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertNotIn("private", repr(projected))

    def test_rejects_unbounded_outer_shapes(self) -> None:
        for value in (None, [], [page(i, 0, []) for i in range(6)]):
            with self.subTest(shape=type(value).__name__), self.assertRaises(SiteVlanNetworkError):
                project_site_vlan_networks(value)


class SiteVlanNetworkClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_two_fixed_pages_and_projects_redacted_summary(self) -> None:
        responses = [
            {"result": page(1, 101, [{"purpose": "0", "id": "hidden", "vlan": 20} for _ in range(100)])},
            {"result": page(2, 101, [{"purpose": "1", "id": "hidden-too", "vlan": 30}])},
        ]
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", side_effect=responses) as request:
            result = self.client.read_site_vlan_network_summary(self.site_ref)
        self.assertEqual(request.call_args_list[0].args,
                         ("GET", "/openapi/v1/ctrl/sites/site_internal/networks/vlans?page=1&pageSize=100"))
        self.assertEqual(request.call_args_list[1].args,
                         ("GET", "/openapi/v1/ctrl/sites/site_internal/networks/vlans?page=2&pageSize=100"))
        self.assertEqual(result["data"]["returned_row_count"], 101)
        self.assertFalse(result["partial"])
        self.assertNotIn("hidden", repr(result))

    def test_rejects_unknown_site_and_path_guard_rejects_unbounded_query(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_vlan_network_summary("7" * 24)
        self.assertTrue(self.client._site_vlan_network_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/networks/vlans?page=5&pageSize=100"))
        for path in (
                "/openapi/v1/other/sites/site_internal/networks/vlans?page=1&pageSize=100",
                "/openapi/v1/ctrl/sites/site_internal/networks/vlans?page=6&pageSize=100",
                "/openapi/v1/ctrl/sites/site_internal/networks/vlans?page=1&pageSize=100&searchKey=x"):
            self.assertFalse(self.client._site_vlan_network_request_valid(path))


if __name__ == "__main__":
    unittest.main()
