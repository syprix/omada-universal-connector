from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_oui_profile_list_summary import (
    SiteOuiProfileListError, project_site_oui_profile_list_page,
)


SITE_REF = "a" * 24


def _grid(rows: list[object], *, total: int | None = None,
          page: int = 1, size: int | None = None) -> dict[str, object]:
    reported_total = len(rows) if total is None else total
    return {"totalRows": reported_total,
            "currentPage": page, "currentSize": len(rows) if size is None else size,
            "data": rows, "totalCount": reported_total}


class SiteOuiProfileProjectionTests(unittest.TestCase):
    def test_projects_documented_profile_and_nested_field_coverage_only(self) -> None:
        result = project_site_oui_profile_list_page(_grid([
            {"id": "private-profile-id", "name": "private-profile-name", "count": 2,
             "ouiCombine": [{"oui": "AABBCCDDEEFF", "description": "private-description"}]},
        ]), page_size=100)
        self.assertEqual(result["profile_count"], 1)
        self.assertEqual(result["reported_total_profiles"], 1)
        self.assertEqual(result["oui_entry_count"], 1)
        self.assertFalse(result["partial"])
        for private in ("private-profile-id", "private-profile-name", "AABBCCDDEEFF",
                        "private-description"):
            self.assertNotIn(private, repr(result))

    def test_first_page_limit_is_explicitly_partial(self) -> None:
        result = project_site_oui_profile_list_page(
            _grid([{"id": "x", "name": "n", "count": 1, "ouiCombine": []}], total=101),
            page_size=100)
        self.assertEqual(result["omitted_profile_count"], 100)
        self.assertTrue(result["partial"])

    def test_total_rows_must_fit_nonnegative_int64_before_projection(self) -> None:
        valid_first_page = [{"id": "x", "name": "n", "count": 1, "ouiCombine": []}]
        with self.assertRaisesRegex(SiteOuiProfileListError, "response_invalid"):
            project_site_oui_profile_list_page(
                _grid(valid_first_page, total=1 << 63), page_size=100)

        result = project_site_oui_profile_list_page(
            _grid(valid_first_page, total=(1 << 63) - 1), page_size=100)
        self.assertEqual(result["reported_total_profiles"], (1 << 63) - 1)
        self.assertEqual(result["omitted_profile_count"], (1 << 63) - 2)
        self.assertTrue(result["partial"])

    def test_missing_invalid_unknown_and_oversized_fields_are_counted_or_rejected(self) -> None:
        result = project_site_oui_profile_list_page(_grid([
            {"name": "", "count": True, "ouiCombine": [
                {"oui": 4, "description": "x", "unknown": "do-not-return"},
                None,
            ], "extra": "hidden"},
        ]), page_size=100)
        self.assertTrue(result["partial"])
        self.assertGreater(result["missing_field_count"], 0)
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertEqual(result["invalid_oui_entry_count"], 1)
        self.assertNotIn("hidden", repr(result))
        for raw in (None, [], {"data": [], "totalRows": 0},
                    _grid([], page=2), _grid([], total=1),
                    _grid([], size=101)):
            with self.subTest(raw=repr(type(raw))):
                with self.assertRaises(SiteOuiProfileListError):
                    project_site_oui_profile_list_page(raw, page_size=100)


class SiteOuiProfileClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", page_size=200,
            max_pages=20, cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"

    def test_fixed_site_bound_first_page_and_redacted_projection(self) -> None:
        page = _grid([{"id": "private", "name": "secret", "count": 1,
                       "ouiCombine": [{"oui": "001122334455", "description": "secret-desc"}]}],
                     total=140)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": page}) as req:
            result = self.client.read_site_oui_profile_list_summary(SITE_REF)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/oui-profiles?page=1&pageSize=100",
            token="token")
        self.assertEqual(result["omitted_profile_count"], 139)
        self.assertTrue(result["partial"])
        for private in ("private", "secret", "001122334455", "secret-desc"):
            self.assertNotIn(private, repr(result))

    def test_configured_smaller_page_is_used_without_followup(self) -> None:
        self.client.config = OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", page_size=25,
            max_pages=20, cert_sha256="a" * 64)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json",
                             return_value={"result": _grid([], total=0)}) as req:
            result = self.client.read_site_oui_profile_list_summary(SITE_REF)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/oui-profiles?page=1&pageSize=25",
            token="token")
        self.assertFalse(result["partial"])

    def test_bad_site_or_unapproved_path_stops(self) -> None:
        with patch.object(self.client, "_request_json") as req:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_oui_profile_list_summary("b" * 24)
        self.assertTrue(self.client._site_oui_profile_list_request_valid(
            "/openapi/v1/ctrl/sites/site_1/oui-profiles?page=1&pageSize=100"))
        for path in (
            "/openapi/v1/ctrl/sites/site_1/oui-profiles?page=2&pageSize=100",
            "/openapi/v1/ctrl/sites/site_1/oui-profiles?page=1&pageSize=101",
            "/openapi/v1/other/sites/site_1/oui-profiles?page=1&pageSize=100",
            "/openapi/v1/ctrl/sites/site_1/oui-profiles/all",
        ):
            with self.subTest(path=path):
                self.assertFalse(self.client._site_oui_profile_list_request_valid(path))
        req.assert_not_called()

    def test_transport_guard_allows_only_the_fixed_first_page(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/oui-profiles?page=1&pageSize=100"
        rejected = (
            "/openapi/v1/ctrl/sites/site_1/oui-profiles?page=2&pageSize=100",
            "/openapi/v1/ctrl/sites/site_1/oui-profiles?page=1&pageSize=101",
            "/openapi/v1/ctrl/sites/site_1/oui-profiles/all",
        )
        with patch.object(self.client, "_connection",
                          side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed, token="token")
            for path in rejected:
                with self.subTest(path=path):
                    with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                        self.client._request_json("GET", path, token="token")


if __name__ == "__main__":
    unittest.main()
