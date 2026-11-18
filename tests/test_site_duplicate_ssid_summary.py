from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_duplicate_ssid_summary import (
    DuplicateSsidProjectionError, project_duplicate_ssid_summary,
)


class DuplicateSsidSummaryProjectionTests(unittest.TestCase):
    def test_returns_counts_without_ssid_names_or_site_id(self) -> None:
        projected = project_duplicate_ssid_summary({
            "ssidNameMap": {"Private SSID": 3, "Hidden WLAN": 2},
            "duplicateSsidNames": ["Private SSID", "Hidden WLAN"],
            "siteId": "site_1",
        }, "site_1")
        self.assertEqual(projected, {
            "unknown_field_count": 0,
            "duplicate_name_map_entries": 2,
            "duplicate_ssid_count_sum": 5,
            "duplicate_name_count": 2,
            "site_id_match": True,
            "partial": False,
        })
        self.assertNotIn("Private SSID", str(projected))
        self.assertNotIn("site_1", str(projected))

    def test_missing_inconsistent_or_unknown_fields_are_reported_partial(self) -> None:
        partial = project_duplicate_ssid_summary({
            "ssidNameMap": {"Private SSID": 2},
            "duplicateSsidNames": ["Different SSID"],
            "siteId": "site_1",
            "futureField": "secret value",
        }, "site_1")
        self.assertTrue(partial["partial"])
        self.assertEqual(partial["unknown_field_count"], 1)
        self.assertNotIn("secret value", str(partial))
        missing = project_duplicate_ssid_summary({}, "site_1")
        self.assertTrue(missing["partial"])
        self.assertIsNone(missing["duplicate_name_count"])

    def test_rejects_oversize_invalid_counts_and_foreign_site(self) -> None:
        invalid = (
            {"ssidNameMap": {"x": True}},
            {"ssidNameMap": {"x": -1}},
            {"duplicateSsidNames": ["x"] * 257},
            {"siteId": "other_site"},
        )
        for source in invalid:
            with self.subTest(source=source):
                with self.assertRaises(DuplicateSsidProjectionError):
                    project_duplicate_ssid_summary(source, "site_1")


class DuplicateSsidSummaryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_uses_fixed_site_route_and_projects_redacted_summary(self) -> None:
        paths = []
        source = {"ssidNameMap": {"Sensitive WLAN": 4},
                  "duplicateSsidNames": ["Sensitive WLAN"], "siteId": "site_1"}
        def request(method, path, **kwargs):
            paths.append((method, path))
            return {"result": source}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_site_duplicate_ssid_summary(self.site_ref)
        self.assertEqual(paths, [("GET", "/openapi/v1/ctrl/sites/site_1/wireless-network/ssids/duplicate-name")])
        self.assertEqual(result["data"]["duplicate_name_count"], 1)
        self.assertNotIn("Sensitive WLAN", str(result))
        self.assertNotIn("site_1", str(result))

    def test_unknown_site_and_invalid_response_fail_closed(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_duplicate_ssid_summary("b" * 24)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"siteId": "wrong"}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_duplicate_ssid_summary(self.site_ref)

    def test_allowlist_accepts_only_fixed_get(self) -> None:
        path = "/openapi/v1/ctrl/sites/site_1/wireless-network/ssids/duplicate-name"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("DELETE", path)


if __name__ == "__main__":
    unittest.main()
