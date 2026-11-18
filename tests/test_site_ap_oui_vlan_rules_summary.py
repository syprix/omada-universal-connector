from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_ap_oui_vlan_rules_summary import (
    ApOuiVlanRulesError, project_site_ap_oui_vlan_rules_summary,
)


SITE_REF = "a" * 24


def _page(rows: list[dict[str, object]], *, total: int | None = None) -> dict[str, object]:
    return {"totalRows": len(rows) if total is None else total,
            "currentPage": 1, "currentSize": 100, "data": rows}


class ApOuiVlanRulesProjectionTests(unittest.TestCase):
    def test_counts_rule_state_and_nested_assignments_without_values(self) -> None:
        result = project_site_ap_oui_vlan_rules_summary(_page([
            {"id": "private-rule-id", "name": "private-rule", "enable": True,
             "ssidList": [{"ssidId": "private-ssid-id", "ssidName": "private-ssid"}],
             "ruleCombine": [{"vlanId": 120, "priority": 3,
                              "ouiProfileId": "private-profile-id",
                              "ouiProfileName": "private-profile"}]},
            {"id": "another-id", "enable": False, "ssidList": [], "ruleCombine": []},
        ]))
        self.assertEqual(result["total_rules"], 2)
        self.assertEqual(result["enabled_rules"], 1)
        self.assertEqual(result["disabled_rules"], 1)
        self.assertEqual(result["ssid_binding_count"], 1)
        self.assertEqual(result["vlan_assignment_count"], 1)
        self.assertEqual(result["priority_counts"], {"3": 1})
        self.assertFalse(result["partial"])
        for private in ("private-rule-id", "private-rule", "private-ssid-id",
                        "private-ssid", "private-profile-id", "private-profile", "120"):
            self.assertNotIn(private, repr(result))

    def test_missing_and_unknown_values_mark_partial_without_zero_fabrication(self) -> None:
        result = project_site_ap_oui_vlan_rules_summary(_page([
            {"enable": "yes", "extra": "hidden", "ssidList": [{"extra": "hidden"}]},
        ]))
        self.assertTrue(result["partial"])
        self.assertEqual(result["rule_state_unknown"], 1)
        self.assertEqual(result["vlan_assignment_count"], 0)
        self.assertGreaterEqual(result["invalid_field_count"], 1)
        self.assertGreaterEqual(result["unknown_field_count"], 2)
        self.assertNotIn("hidden", repr(result))

    def test_malformed_grid_and_nested_lists_fail_closed_or_mark_invalid(self) -> None:
        for raw in (None, [], {"totalRows": 2, "data": []},
                    {"totalRows": 1, "data": [None]},
                    {"totalRows": 10_001, "data": []}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ApOuiVlanRulesError):
                project_site_ap_oui_vlan_rules_summary(raw)
        malformed = project_site_ap_oui_vlan_rules_summary(_page([
            {"enable": True, "ssidList": "bad", "ruleCombine": [
                {"vlanId": 1, "priority": 8, "ouiProfileId": 4},
            ]},
        ]))
        self.assertTrue(malformed["partial"])
        self.assertGreaterEqual(malformed["invalid_field_count"], 4)


class ApOuiVlanRulesClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"

    def test_reads_fixed_paginated_route_and_returns_only_summary(self) -> None:
        page = _page([{"id": "private", "name": "hidden", "enable": True,
                       "ssidList": [{"ssidName": "hidden-ssid"}],
                       "ruleCombine": [{"vlanId": 50, "priority": 1,
                                        "ouiProfileId": "hidden-profile"}]}])
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": page}) as request:
            result = self.client.read_site_ap_oui_vlan_rules_summary(SITE_REF)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/ap-oui-rules?page=1&pageSize=100",
            token="token")
        self.assertEqual(result["resource"], "site_ap_oui_vlan_rules_summary")
        self.assertNotIn("hidden", repr(result))
        self.assertNotIn("50", repr(result))

    def test_reads_all_pages_with_fixed_query_values(self) -> None:
        self.client.config = OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", page_size=1,
            max_pages=2, cert_sha256="a" * 64)
        pages = [
            {"result": {**_page([{"enable": True, "ruleCombine": []}], total=2),
                        "currentPage": 1, "currentSize": 1}},
            {"result": {**_page([{"enable": False, "ruleCombine": []}], total=2),
                        "currentPage": 2, "currentSize": 1}},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=pages) as request:
            result = self.client.read_site_ap_oui_vlan_rules_summary(SITE_REF)
        self.assertEqual(result["total_rules"], 2)
        self.assertEqual(result["enabled_rules"], 1)
        self.assertEqual(result["disabled_rules"], 1)
        self.assertEqual(request.call_args_list[0].args[:2],
                         ("GET", "/openapi/v1/ctrl/sites/site_1/ap-oui-rules?page=1&pageSize=1"))
        self.assertEqual(request.call_args_list[1].args[:2],
                         ("GET", "/openapi/v1/ctrl/sites/site_1/ap-oui-rules?page=2&pageSize=1"))

    def test_unknown_site_and_unsafe_query_stop_before_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_ap_oui_vlan_rules_summary("b" * 24)
        route = "/openapi/v1/ctrl/sites/site_1/ap-oui-rules?page=1&pageSize=100"
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", route + "&sort=private")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
