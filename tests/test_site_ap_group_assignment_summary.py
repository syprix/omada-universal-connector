from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_ap_group_assignment_summary import summarize_ap_group_assignments
from app.site_ap_group_info_summary import summarize_ap_group_info


SITE_REF = "a" * 24


def _page(rows: list[object], total: int | None = None) -> dict[str, object]:
    return {"totalRows": len(rows) if total is None else total,
            "currentPage": 1, "currentSize": 100, "data": rows}


class ApGroupAssignmentProjectionTests(unittest.TestCase):
    def test_counts_assignments_and_overrides_without_device_values(self):
        result = summarize_ap_group_assignments([
            {"id": "private-device", "name": "private-ap", "ip": "192.0.2.8",
             "apGroupId": "private-group", "apGroupName": "private group",
             "overrideNum": 2, "traffic": 93824},
            {"apGroupId": "", "overrideNum": 0, "mac": "00:11:22:33:44:55"},
        ])
        self.assertEqual(result["ap_rows"], 2)
        self.assertEqual(result["with_reported_group_assignment"], 1)
        self.assertEqual(result["without_reported_group_assignment"], 1)
        self.assertEqual(result["rows_with_ssid_overrides"], 1)
        self.assertEqual(result["reported_ssid_override_total"], 2)
        self.assertFalse(result["partial"])
        for private in ("private-device", "private-ap", "192.0.2.8", "private-group",
                        "private group", "93824", "00:11:22:33:44:55"):
            self.assertNotIn(private, repr(result))

    def test_missing_and_invalid_values_are_not_zero(self):
        result = summarize_ap_group_assignments([
            {"apGroupId": 22, "overrideNum": -1}, {"apGroupId": None}, None,
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["group_assignment_unknown"], 1)
        self.assertEqual(result["override_value_missing_rows"], 1)
        self.assertEqual(result["reported_ssid_override_total"], None)
        self.assertEqual(result["malformed_rows_or_values"], 2)

    def test_rejects_unbounded_or_wrong_container(self):
        for rows in (None, {}, [None] * 10_001):
            with self.subTest(rows_type=type(rows).__name__), self.assertRaises(ValueError):
                summarize_ap_group_assignments(rows)


class ApGroupInfoProjectionTests(unittest.TestCase):
    def test_reports_documented_capacity_and_redacts_group_labels(self):
        result = summarize_ap_group_info({
            "id": "private-group-id", "name": "private-group", "primary": True,
            "apNum": 4, "remainingBinding": {"0": 5, "1": 3, "2": 2},
            "ssidNameList": ["private-ssid"],
        })
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["resource"], "site_ap_group_info_summary")
        self.assertEqual(result["primary"], True)
        self.assertEqual(result["ap_count"], 4)
        self.assertEqual(result["remaining_ssid_bindings"], {"2g": 5, "5g": 3, "6g": 2})
        self.assertFalse(result["partial"])
        for private in ("private-group-id", "private-group", "private-ssid"):
            self.assertNotIn(private, repr(result))

    def test_missing_fields_remain_unknown(self):
        result = summarize_ap_group_info({"primary": "true", "apNum": -1,
                                          "remainingBinding": {"0": True}})
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["partial"])
        self.assertIsNone(result["primary"])
        self.assertIsNone(result["ap_count"])
        self.assertIsNone(result["remaining_ssid_bindings"]["2g"])
        self.assertIsNone(result["remaining_ssid_bindings"]["5g"])


class ApGroupClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"

    def test_reads_bounded_site_assignment_pages_and_returns_counts(self):
        result = {"errorCode": 0, "result": _page([
            {"apGroupId": "raw-group", "apGroupName": "private", "overrideNum": 1,
             "name": "private AP", "mac": "00:11:22:33:44:55"},
            {"overrideNum": 0},
        ])}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=result) as request:
            summary = self.client.read_site_ap_group_assignment_summary(SITE_REF)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/ap-groups/aps?page=1&pageSize=100",
            token="token")
        self.assertEqual(summary["with_reported_group_assignment"], 1)
        self.assertEqual(summary["reported_ssid_override_total"], 1)
        for private in ("raw-group", "private", "private AP", "00:11:22:33:44:55"):
            self.assertNotIn(private, repr(summary))

    def test_selected_group_is_freshly_bound_by_opaque_inventory_ref(self):
        raw_id = "private-group-id"
        group_ref = self.client._opaque_ref("ap_group", "site_1:" + raw_id)
        pages = [
            {"errorCode": 0, "result": _page([{
                "id": raw_id, "name": "private group", "primary": True, "apNum": 4,
                "remainingBinding": {"0": 5, "1": 3, "2": 2},
                "ssidNameList": ["private-ssid"],
            }])},
            {"errorCode": 0, "result": {
                "id": raw_id, "name": "private group", "primary": True, "apNum": 4,
                "remainingBinding": {"0": 5, "1": 3, "2": 2},
                "ssidNameList": ["private-ssid"],
            }},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=pages) as request:
            summary = self.client.read_site_ap_group_info_summary(SITE_REF, group_ref)
        self.assertEqual(request.call_args_list[0].args[:2], (
            "GET", "/openapi/v1/ctrl/sites/site_1/ap-groups?page=1&pageSize=100"))
        self.assertEqual(request.call_args_list[1].args[:2], (
            "GET", "/openapi/v1/ctrl/sites/site_1/ap-groups/private-group-id/info"))
        self.assertEqual(summary["group_ref"], group_ref)
        self.assertEqual(summary["remaining_ssid_bindings"]["5g"], 3)
        for private in (raw_id, "private group", "private-ssid"):
            self.assertNotIn(private, repr(summary))

    def test_unknown_or_ambiguous_group_reference_stops_before_detail_read(self):
        base_row = {"id": "same-group", "primary": True, "apNum": 2}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "result": _page([base_row, base_row]),
                }) as request:
            group_ref = self.client._opaque_ref("ap_group", "site_1:same-group")
            with self.assertRaisesRegex(OpenApiError, "ap_group_ref_ambiguous"):
                self.client.read_site_ap_group_info_summary(SITE_REF, group_ref)
        request.assert_called_once()

    def test_fixed_assignment_and_group_info_paths_reject_extra_input(self):
        assignment = "/openapi/v1/ctrl/sites/site_1/ap-groups/aps?page=1&pageSize=100"
        group_info = "/openapi/v1/ctrl/sites/site_1/ap-groups/group_1/info"
        self.assertTrue(self.client._site_ap_group_assignment_request_valid(assignment))
        self.assertTrue(self.client._site_ap_group_info_request_valid(group_info))
        self.assertFalse(self.client._site_ap_group_assignment_request_valid(assignment + "&filter=x"))
        self.assertFalse(self.client._site_ap_group_assignment_request_valid(
            assignment.replace("pageSize=100", "pageSize=99")))
        self.assertFalse(self.client._site_ap_group_info_request_valid(group_info + "?name=x"))


if __name__ == "__main__":
    unittest.main()
