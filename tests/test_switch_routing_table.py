from __future__ import annotations

import unittest

from app.switch_routing_table import SwitchRoutingTableError, summarize_switch_routing_table


class SwitchRoutingTableSummaryTests(unittest.TestCase):
    def test_counts_route_types_and_values_without_addresses(self) -> None:
        rows = [{"type": "static", "distance": 1, "metric": 10,
                 "destinationIp": "192.0.2.0/24", "nextHop": "192.0.2.1", "interfaceName": ["private-lan"]},
                {"type": "static", "distance": 1, "metric": 20,
                 "destinationIp": "198.51.100.0/24", "nextHops": ["198.51.100.1"]}]
        result = summarize_switch_routing_table(rows)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["summary"]["by_type"], {"static": 2})
        self.assertEqual(result["summary"]["by_distance"], {1: 2})
        self.assertEqual(result["summary"]["by_metric"], {10: 1, 20: 1})
        for secret in ("192.0.2", "198.51.100", "private-lan", "destinationIp", "nextHop"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_and_excess_categories_are_counted_as_unknown(self) -> None:
        bad = summarize_switch_routing_table([{"type": "bad" * 24, "distance": True, "metric": -1}])
        self.assertTrue(bad["partial"])
        self.assertEqual(bad["summary"]["unknown_rows"], 1)
        rows = [{"type": f"type-{n}", "distance": n, "metric": n} for n in range(65)]
        capped = summarize_switch_routing_table(rows)
        self.assertEqual(len(capped["summary"]["by_type"]), 64)
        self.assertEqual(capped["summary"]["unknown_rows"], 1)

    def test_rejects_over_limit(self) -> None:
        with self.assertRaises(SwitchRoutingTableError):
            summarize_switch_routing_table([{}] * 10_001)


if __name__ == "__main__":
    unittest.main()
