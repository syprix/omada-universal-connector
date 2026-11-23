import unittest

from app.site_nat_exception_summary import (
    SiteNatExceptionSummaryError, summarize_site_nat_exceptions,
)


class SiteNatExceptionSummaryTests(unittest.TestCase):
    @staticmethod
    def page(current: int, total: int, rows: list[object], size: int) -> dict[str, object]:
        return {"totalRows": total, "currentPage": current,
                "currentSize": size, "data": rows}

    @staticmethod
    def row(name: str, status: bool, lan: list[str], interface: str, rule_id: str) -> dict[str, object]:
        return {"id": rule_id, "name": name, "status": status, "lanList": lan,
                "interface": interface, "description": "private description"}

    def test_counts_configuration_and_omits_rule_names_ids_and_network_values(self):
        result = summarize_site_nat_exceptions([
            self.page(1, 2, [self.row("private rule one", True,
                                     ["private-lan-id-1", "private-lan-id-2"],
                                     "private-wan-id", "private-rule-id-1")], 100),
            self.page(2, 2, [self.row("private rule two", False, [], "", "private-rule-id-2")], 1),
        ])
        self.assertEqual(result["reported_rule_count"], 2)
        self.assertEqual(result["rule_status_counts"],
                         {"enabled": 1, "disabled": 1, "unreported": 0})
        self.assertEqual(result["lan_entry_count"], 2)
        self.assertFalse(result["partial"])
        rendered = repr(result)
        for secret in ("private rule", "private-lan-id", "private-wan-id",
                       "private-rule-id", "private description"):
            self.assertNotIn(secret, rendered)

    def test_incomplete_page_unknown_status_and_truncation_are_reported(self):
        result = summarize_site_nat_exceptions([
            self.page(1, 2, [{"name": "private", "status": "enabled"}], 100)
        ])
        self.assertTrue(result["partial"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["rule_status_counts"]["unreported"], 1)
        self.assertGreater(result["missing_field_count"], 0)

    def test_empty_or_malformed_page_set_is_rejected(self):
        with self.assertRaises(SiteNatExceptionSummaryError):
            summarize_site_nat_exceptions([])
        partial = summarize_site_nat_exceptions([None])
        self.assertTrue(partial["partial"])
        self.assertEqual(partial["invalid_field_count"], 1)


if __name__ == "__main__":
    unittest.main()
