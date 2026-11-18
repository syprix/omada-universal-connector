from __future__ import annotations

import unittest

from app.switch_vrfs import SwitchVrfsError, summarize_switch_vrfs


class SwitchVrfSummaryTests(unittest.TestCase):
    def test_counts_documented_fields_and_drops_names_and_identifiers(self) -> None:
        rows = [
            {"id": "private-vrf-id", "vrf": "private-vrf-name", "ipv4Enable": True,
             "ipv6Enable": False, "isDefault": True, "resource": 0},
            {"id": "another-private-id", "vrf": "another-private-name", "ipv4Enable": False,
             "ipv6Enable": True, "isDefault": False, "resource": 1},
        ]
        result = summarize_switch_vrfs(rows)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["summary"], {
            "by_ipv4_enabled": {"false": 1, "true": 1},
            "by_ipv6_enabled": {"false": 1, "true": 1},
            "default_count": 1,
            "by_resource_code": {0: 1, 1: 1},
            "unknown_rows": 0,
        })
        for private_value in ("private-vrf-id", "private-vrf-name", "another-private-id",
                              "another-private-name", "ipv4Enable"):
            self.assertNotIn(private_value, repr(result))

    def test_counts_invalid_rows_without_returning_any_source_data(self) -> None:
        result = summarize_switch_vrfs([
            {"ipv4Enable": 1, "ipv6Enable": None, "isDefault": False, "resource": 9},
            None,
        ])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["summary"]["unknown_rows"], 2)
        self.assertTrue(result["partial"])

    def test_rejects_over_limit(self) -> None:
        with self.assertRaises(SwitchVrfsError):
            summarize_switch_vrfs([{}] * 10_001)


if __name__ == "__main__":
    unittest.main()
