from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_group_profiles_coverage import (
    MAX_GROUP_PROFILE_ROWS, MISSING_GROUP_PROFILES_RESULT,
    SiteGroupProfilesCoverageError, project_site_group_profiles_coverage,
)


SITE_REF = "a" * 24


class SiteGroupProfilesProjectionTests(unittest.TestCase):
    def test_empty_missing_and_invalid_result_are_distinct(self) -> None:
        empty = project_site_group_profiles_coverage([])
        missing = project_site_group_profiles_coverage(MISSING_GROUP_PROFILES_RESULT)
        self.assertEqual(empty["source_state"], "empty")
        self.assertFalse(empty["partial"])
        self.assertEqual(missing["source_state"], "missing")
        self.assertIsNone(missing["row_count"])
        self.assertTrue(missing["partial"])
        for invalid in (None, {}, "rows"):
            with self.subTest(invalid=type(invalid).__name__):
                with self.assertRaisesRegex(SiteGroupProfilesCoverageError,
                                            "response_invalid"):
                    project_site_group_profiles_coverage(invalid)

    def test_documented_field_presence_and_types_are_counted_without_values(self) -> None:
        result = project_site_group_profiles_coverage([{
            "groupId": "private-id", "name": "private-label", "type": 2,
            "count": 3, "buildIn": True, "portType": 1, "description": "private",
            "ipList": ["192.0.2.1"], "ipv6List": [], "portList": ["secret-port"],
            "portMaskList": [], "macAddressList": ["secret-mac"],
            "countryList": ["secret-country"], "domainName": ["secret-domain"],
            "domainNamePort": ["secret-domain-port"],
        }])
        self.assertEqual(result["source_state"], "nonempty")
        self.assertEqual(result["row_count"], 1)
        self.assertFalse(result["partial"])
        for field in ("type", "count", "buildIn"):
            self.assertEqual(result["field_coverage"][field],
                             {"present": 1, "type_valid": 1, "missing": 0, "invalid": 0})
        self.assertFalse(result["identifiers_labels_values_and_list_elements_returned"])
        for secret in ("private-id", "private-label", "192.0.2.1", "secret-port",
                       "secret-mac", "secret-country", "secret-domain", "private"):
            self.assertNotIn(secret, repr(result))

    def test_malformed_rows_fields_and_unknown_names_are_only_counted(self) -> None:
        result = project_site_group_profiles_coverage([
            {"type": True, "count": 1 << 40, "buildIn": 1,
             "ipList": "not-inspected", "private-unknown-key": "private-value"},
            None,
            {"extra": "not-output"} | {f"key{i}": i for i in range(32)},
        ])
        self.assertEqual(result["invalid_row_count"], 2)
        self.assertEqual(result["field_coverage"]["type"]["invalid"], 1)
        self.assertEqual(result["field_coverage"]["count"]["invalid"], 1)
        self.assertEqual(result["field_coverage"]["buildIn"]["invalid"], 1)
        self.assertEqual(result["field_coverage"]["ipList"]["invalid"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        for secret in ("private-unknown-key", "private-value", "not-output"):
            self.assertNotIn(secret, repr(result))

    def test_row_bound_marks_omitted_rows_partial(self) -> None:
        rows = [{} for _ in range(MAX_GROUP_PROFILE_ROWS + 1)]
        result = project_site_group_profiles_coverage(rows)
        self.assertEqual(result["row_count"], MAX_GROUP_PROFILE_ROWS + 1)
        self.assertEqual(result["inspected_row_count"], MAX_GROUP_PROFILE_ROWS)
        self.assertEqual(result["omitted_row_count"], 1)
        self.assertTrue(result["partial"])


class SiteGroupProfilesClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", page_size=100,
            max_pages=5, cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"

    def test_fixed_site_bound_get_has_no_query_and_returns_only_coverage(self) -> None:
        raw = {"groupId": "secret-id", "name": "secret-name", "type": 4,
               "count": 7, "buildIn": False, "ipList": ["secret-value"]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": [raw]}) as req:
            result = self.client.read_site_group_profiles_coverage(SITE_REF)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/profiles/groups", token="token")
        self.assertNotIn("site_ref", result)
        self.assertNotIn("secret-id", repr(result))
        self.assertNotIn("secret-name", repr(result))
        self.assertNotIn("secret-value", repr(result))

    def test_missing_result_is_reported_and_invalid_result_fails_closed(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={}) as req:
            result = self.client.read_site_group_profiles_coverage(SITE_REF)
        self.assertEqual(result["source_state"], "missing")
        req.assert_called_once()
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": None}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_group_profiles_coverage(SITE_REF)

    def test_unknown_site_and_alternate_paths_are_rejected(self) -> None:
        with patch.object(self.client, "_request_json") as req:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_group_profiles_coverage("b" * 24)
        self.assertFalse(req.called)
        self.assertTrue(self.client._site_group_profiles_coverage_request_valid(
            "/openapi/v1/ctrl/sites/site_1/profiles/groups"))
        for path in (
            "/openapi/v1/ctrl/sites/site_1/profiles/groups?type=1",
            "/openapi/v1/ctrl/sites/site_1/profiles/groups/1",
            "/openapi/v1/other/sites/site_1/profiles/groups",
        ):
            with self.subTest(path=path):
                self.assertFalse(self.client._site_group_profiles_coverage_request_valid(path))


if __name__ == "__main__":
    unittest.main()
