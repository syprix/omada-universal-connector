from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_ap_group_summary import ApGroupSummaryError, project_site_ap_group_summary


SITE_REF = "a" * 24


def _page(rows: list[dict[str, object]], *, total: int | None = None) -> dict[str, object]:
    return {
        "totalRows": len(rows) if total is None else total,
        "currentPage": 1,
        "currentSize": 100,
        "data": rows,
        "maxSsids2G": 8,
        "maxSsids5G": 8,
        "maxSsids6G": 8,
        "maxSsidsMlo": 4,
    }


class SiteApGroupSummaryProjectionTests(unittest.TestCase):
    def test_summarizes_counts_and_drops_group_and_ssid_labels(self) -> None:
        result = project_site_ap_group_summary(_page([
            {"id": "private-group-id", "name": "private-group-name", "primary": True,
             "apNum": 3, "remainingBinding": {"0": 2, "1": 4, "2": 1},
             "ssidNameList": ["private-ssid"]},
            {"id": "another-id", "name": "another-name", "primary": False,
             "apNum": 2, "remainingBinding": {"0": 1, "1": 2, "2": 3},
             "ssidNameList": []},
        ]))
        self.assertEqual(result["total_groups"], 2)
        self.assertEqual(result["primary_groups"], 1)
        self.assertEqual(result["non_primary_groups"], 1)
        self.assertEqual(result["ap_count_total"], 5)
        self.assertEqual(result["groups_with_ssid_list"], 2)
        self.assertEqual(result["remaining_ssid_bindings"]["5g"]["count"], 6)
        self.assertEqual(result["max_ssids_by_band"], {"2g": 8, "5g": 8, "6g": 8, "mlo": 4})
        self.assertFalse(result["partial"])
        for private in ("private-group-id", "private-group-name", "private-ssid", "another-id"):
            self.assertNotIn(private, repr(result))

    def test_missing_optional_counts_are_unknown_not_zero(self) -> None:
        result = project_site_ap_group_summary({
            "totalRows": 1, "currentPage": 1, "currentSize": 100,
            "data": [{"primary": True}],
        })
        self.assertTrue(result["partial"])
        self.assertIsNone(result["ap_count_total"])
        self.assertEqual(result["ap_count_known_groups"], 0)
        self.assertEqual(result["remaining_ssid_bindings"]["2g"]["unknown_groups"], 1)

    def test_invalid_optional_values_and_unknown_fields_are_counted(self) -> None:
        result = project_site_ap_group_summary({
            **_page([{"primary": 1, "apNum": -1, "ssidNameList": "hidden",
                      "remainingBinding": {"0": True}, "extra": "hidden"}]),
            "extraGridField": "hidden",
        })
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["invalid_field_count"], 4)
        self.assertGreaterEqual(result["unknown_field_count"], 2)
        self.assertNotIn("hidden", repr(result))

    def test_invalid_grid_shapes_fail_closed(self) -> None:
        for raw in (None, [], {"totalRows": 2, "data": []},
                    {"totalRows": 1, "data": [None]},
                    {"totalRows": 1, "data": [{"primary": True}] * 10_001}):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(ApGroupSummaryError):
                project_site_ap_group_summary(raw)


class SiteApGroupSummaryClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"

    def test_reads_fixed_paged_route_and_returns_redacted_summary(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": _page([{"id": "private", "name": "private", "primary": True,
                                      "apNum": 2, "ssidNameList": ["hidden"]}])}) as request:
            result = self.client.read_site_ap_group_summary(SITE_REF)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/ap-groups?page=1&pageSize=100", token="token")
        self.assertEqual(result["resource"], "site_ap_group_summary")
        self.assertEqual(result["ap_count_total"], 2)
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(result["groups"][0]["group_ref"],
                         self.client._opaque_ref("ap_group", "site_1:private"))
        self.assertEqual(result["groups"][0]["primary"], True)
        self.assertEqual(result["groups"][0]["ap_count"], 2)
        self.assertNotIn("hidden", repr(result))
        self.assertNotIn('"private"', repr(result))

    def test_reads_all_bounded_pages_before_summarizing(self) -> None:
        self.client.config = OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", page_size=1,
            max_pages=2, cert_sha256="a" * 64)
        pages = [
            {"result": {**_page([{"primary": True, "apNum": 2}], total=2),
                        "currentPage": 1, "currentSize": 1}},
            {"result": {**_page([{"primary": False, "apNum": 3}], total=2),
                        "currentPage": 2, "currentSize": 1}},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=pages) as request:
            result = self.client.read_site_ap_group_summary(SITE_REF)
        self.assertEqual(result["total_groups"], 2)
        self.assertEqual(result["ap_count_total"], 5)
        self.assertEqual(request.call_args_list[0].args[:2],
                         ("GET", "/openapi/v1/ctrl/sites/site_1/ap-groups?page=1&pageSize=1"))
        self.assertEqual(request.call_args_list[1].args[:2],
                         ("GET", "/openapi/v1/ctrl/sites/site_1/ap-groups?page=2&pageSize=1"))

    def test_rejects_total_over_public_item_limit_before_following_pages(self) -> None:
        oversized = {"result": {**_page([], total=10_001), "currentSize": 100}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=oversized) as request:
            with self.assertRaisesRegex(OpenApiError, "openapi_response_limit_exceeded"):
                self.client.read_site_ap_group_summary(SITE_REF)
        request.assert_called_once()

    def test_unknown_site_stops_before_controller_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_ap_group_summary("b" * 24)
        request.assert_not_called()

    def test_fixed_route_query_allowlist(self) -> None:
        route = "/openapi/v1/ctrl/sites/site_1/ap-groups?page=1&pageSize=100"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("reached")):
            with self.assertRaisesRegex(OpenApiError, "reached"):
                self.client._request_json("GET", route)
        for unsafe in (route + "&searchKey=private", route.replace("page=1", "page=0"),
                       route.replace("pageSize=100", "pageSize=99")):
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", unsafe)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("POST", route)


if __name__ == "__main__":
    unittest.main()
