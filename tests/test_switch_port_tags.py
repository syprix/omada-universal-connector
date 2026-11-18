from __future__ import annotations

import unittest

from app.switch_port_tags import SwitchPortTagsError, summarize_switch_port_tags


class SwitchPortTagSummaryTests(unittest.TestCase):
    def test_counts_labels_and_resource_codes_without_names_or_ids(self) -> None:
        result = summarize_switch_port_tags([
            {"tagId": "private-tag-id", "name": "private-tag-name", "resource": 0},
            {"tagId": "private-template-id", "name": "private-template-name", "resource": 1},
            {"tagId": "private-override-id", "name": "private-override-name", "resource": 2},
        ])
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["summary"], {"by_resource_code": {0: 1, 1: 1, 2: 1},
                                              "unknown_rows": 0})
        for secret in ("private-tag-id", "private-tag-name", "private-template-id",
                       "private-template-name", "private-override-id", "private-override-name"):
            self.assertNotIn(secret, repr(result))

    def test_counts_invalid_resource_values_as_unknown(self) -> None:
        result = summarize_switch_port_tags([{"resource": True}, {}, None, {"resource": 3}])
        self.assertEqual(result["summary"], {"by_resource_code": {}, "unknown_rows": 4})
        self.assertTrue(result["partial"])

    def test_rejects_row_limit_excess(self) -> None:
        with self.assertRaises(SwitchPortTagsError):
            summarize_switch_port_tags([{}] * 4097)


if __name__ == "__main__":
    unittest.main()
