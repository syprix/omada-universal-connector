from __future__ import annotations

import json
import unittest

from app.site_session_limit_rule_coverage import (
    MISSING_SESSION_LIMIT_RULE_RESULT,
    SiteSessionLimitRuleCoverageError,
    project_site_session_limit_rule_coverage,
)


class _NoIterList(list):
    def __iter__(self):
        raise AssertionError("list contents must not be inspected")


def _rule(**overrides):
    value = {
        "id": "synthetic-rule-id",
        "index": 7,
        "name": "synthetic-rule-label",
        "status": False,
        "sourceType": 3,
        "sourceIds": _NoIterList(["synthetic-source-ref"]),
        "ip": "synthetic-address",
        "maxSession": 12,
        "existIpAddress": True,
    }
    value.update(overrides)
    return value


def _page(rows, *, total=None, current_page=1, current_size=None, **extra):
    if total is None:
        total = len(rows)
    if current_size is None:
        current_size = len(rows)
    return {"totalRows": total, "currentPage": current_page,
            "currentSize": current_size, "data": rows,
            "supportIpAddress": False, **extra}


class SiteSessionLimitRuleCoverageTests(unittest.TestCase):
    def test_full_page_projects_only_field_and_type_counts(self):
        result = project_site_session_limit_rule_coverage(
            _page([_rule(featureDescription=_NoIterList([{"marker": "synthetic-feature"}]))]))
        encoded = json.dumps(result, sort_keys=True)
        self.assertEqual(result["source_state"], "nonempty")
        self.assertEqual(result["page_state"], "first_page_covers_reported_total")
        self.assertTrue(result["first_page_covers_reported_total"])
        self.assertEqual(result["valid_row_count"], 1)
        self.assertEqual(result["row_field_coverage"]["maxSession"]["type_valid"], 1)
        self.assertEqual(result["row_field_coverage"]["sourceIds"]["type_valid"], 1)
        self.assertEqual(result["row_field_coverage"]["featureDescription"]["type_valid"], 1)
        self.assertEqual(result["support_ip_address_coverage"]["type_valid"], 1)
        self.assertFalse(result["partial"])
        for marker in ("synthetic-rule-id", "synthetic-rule-label", "synthetic-address",
                       "synthetic-source-ref", "synthetic-feature", "maxSession\": 12"):
            self.assertNotIn(marker, encoded)
        self.assertFalse(result["rule_values_identifiers_and_list_entries_returned"])

    def test_documented_boolean_values_are_covered_but_not_returned(self):
        false_result = project_site_session_limit_rule_coverage(
            _page([_rule(status=False)], supportIpAddress=False))
        true_result = project_site_session_limit_rule_coverage(
            _page([_rule(status=True)], supportIpAddress=True))
        self.assertEqual(false_result, true_result)
        self.assertEqual(false_result["row_field_coverage"]["status"]["type_valid"], 1)
        self.assertEqual(false_result["support_ip_address_coverage"]["type_valid"], 1)

    def test_first_page_is_bounded_and_reported_partial_without_follow_on(self):
        result = project_site_session_limit_rule_coverage(
            _page([_rule() for _ in range(100)], total=147, current_size=100))
        self.assertEqual(result["page_size"], 100)
        self.assertEqual(result["returned_row_count"], 100)
        self.assertEqual(result["reported_total_row_count"], 147)
        self.assertEqual(result["reported_remaining_row_count"], 47)
        self.assertEqual(result["page_state"], "first_page_partial")
        self.assertTrue(result["partial"])

    def test_empty_zero_based_example_and_optional_platform_field(self):
        empty = project_site_session_limit_rule_coverage(
            _page([], total=0, current_page=0, current_size=0))
        self.assertEqual(empty["source_state"], "empty")
        self.assertEqual(empty["page_state"], "empty")
        self.assertFalse(empty["partial"])
        optional = project_site_session_limit_rule_coverage(_page([_rule()]))
        self.assertEqual(optional["row_field_coverage"]["featureDescription"]["missing"], 1)
        self.assertEqual(optional["optional_field_absent_count"], 1)
        self.assertFalse(optional["partial"])

    def test_missing_result_and_missing_data_are_distinct_partial_states(self):
        missing_result = project_site_session_limit_rule_coverage(
            MISSING_SESSION_LIMIT_RULE_RESULT)
        missing_data = project_site_session_limit_rule_coverage({
            "totalRows": 0, "currentPage": 1, "currentSize": 0,
            "supportIpAddress": False})
        self.assertEqual(missing_result["source_state"], "result_missing")
        self.assertEqual(missing_data["source_state"], "data_missing")
        self.assertTrue(missing_result["partial"])
        self.assertTrue(missing_data["partial"])

    def test_missing_metadata_and_required_fields_remain_explicitly_partial(self):
        for rows in ([], [_rule()]):
            with self.subTest(row_count=len(rows)):
                missing_total = project_site_session_limit_rule_coverage({
                    "currentPage": 1, "currentSize": len(rows),
                    "data": rows, "supportIpAddress": True})
                encoded = json.dumps(missing_total, sort_keys=True)
                self.assertIsNone(missing_total["reported_total_row_count"])
                self.assertEqual(missing_total["page_state"], "metadata_missing")
                self.assertEqual(missing_total["source_state"],
                                 "empty_total_unknown" if not rows else "nonempty")
                self.assertTrue(missing_total["partial"])
                self.assertIn('"reported_total_row_count": null', encoded)
        explicit_zero = project_site_session_limit_rule_coverage({
            "totalRows": 0, "currentPage": 0, "currentSize": 0,
            "data": [], "supportIpAddress": False})
        self.assertEqual(explicit_zero["reported_total_row_count"], 0)
        self.assertFalse(explicit_zero["partial"])
        required = project_site_session_limit_rule_coverage(
            _page([{"name": "synthetic", "status": True, "sourceType": 1}]))
        self.assertEqual(required["required_field_missing_count"], 1)
        self.assertTrue(required["partial"])

    def test_invalid_field_types_and_unknown_fields_are_counted_without_values(self):
        result = project_site_session_limit_rule_coverage(_page(
            [_rule(maxSession=True, futureField="private-value")],
            supportIpAddress="invalid"))
        self.assertEqual(result["row_field_coverage"]["maxSession"]["invalid"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private-value", repr(result))

    def test_invalid_and_contradictory_pages_are_rejected(self):
        invalid_pages = (
            _page([_rule()], total=True),
            _page([_rule()], total=0),
            _page([], total=1),
            _page([_rule()], current_page=2),
            _page([_rule()], current_size=99),
            _page([_rule() for _ in range(101)], total=101, current_size=100),
            _page([_rule()], total=(1 << 63)),
        )
        for page in invalid_pages:
            with self.subTest(page_state=page.get("currentPage")):
                with self.assertRaises(SiteSessionLimitRuleCoverageError):
                    project_site_session_limit_rule_coverage(page)
        with self.assertRaises(SiteSessionLimitRuleCoverageError):
            project_site_session_limit_rule_coverage(_page([]), page_size=101)


if __name__ == "__main__":
    unittest.main()
