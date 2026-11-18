from __future__ import annotations

import unittest

from app.switch_ospf_neighbors import (
    SwitchOspfNeighborsError,
    summarize_switch_ospf_neighbors,
)


class SwitchOspfNeighborSummaryTests(unittest.TestCase):
    def test_counts_documented_state_values_without_neighbor_identifiers(self) -> None:
        rows = [{"state": "Full", "neighborIp": "192.0.2.5", "routerId": "private-id"},
                {"state": "Full", "neighborInterface": "private-interface"},
                {"state": "2-Way", "processId": "private-process"}]
        result = summarize_switch_ospf_neighbors(rows)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["summary"]["by_state"], {"Full": 2, "2-Way": 1})
        self.assertFalse(result["partial"])
        for secret in ("192.0.2.5", "private-id", "private-interface", "private-process"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_or_missing_state_is_partial(self) -> None:
        result = summarize_switch_ospf_neighbors([{"state": "Full"}, {"state": "too long" * 8}, {}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["summary"], {"by_state": {"Full": 1}, "unknown_state_rows": 2})

    def test_row_limit_fails_closed(self) -> None:
        with self.assertRaises(SwitchOspfNeighborsError):
            summarize_switch_ospf_neighbors([{}] * 10_001)

    def test_state_categories_are_bounded(self) -> None:
        rows = [{"state": f"state-{i}"} for i in range(65)]
        result = summarize_switch_ospf_neighbors(rows)
        self.assertEqual(len(result["summary"]["by_state"]), 64)
        self.assertEqual(result["summary"]["unknown_state_rows"], 1)
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
