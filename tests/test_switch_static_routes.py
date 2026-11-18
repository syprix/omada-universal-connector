from __future__ import annotations

import unittest

from app.switch_static_routes import SwitchStaticRoutesError, summarize_switch_static_routes


class SwitchStaticRouteSummaryTests(unittest.TestCase):
    def test_aggregates_route_codes_and_destination_counts_without_addresses(self) -> None:
        rows = [
            {"status": True, "distance": 1, "destinations": ["192.0.2.0/24"],
             "ipVersion": 0, "resource": 1, "nextHopIp": "192.0.2.1", "name": "private-route"},
            {"status": False, "distance": 10, "destinations": ["2001:db8::/32", "2001:db8:1::/48"],
             "ipVersion": 1, "resource": 2, "nextHopVrfId": "private-vrf"},
        ]
        result = summarize_switch_static_routes(rows, True)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["summary"]["by_status"], {"false": 1, "true": 1})
        self.assertEqual(result["summary"]["by_ip_version"], {0: 1, 1: 1})
        self.assertEqual(result["summary"]["by_distance"], {1: 1, 10: 1})
        self.assertEqual(result["summary"]["by_resource_code"], {1: 1, 2: 1})
        self.assertEqual(result["summary"]["by_destination_count"], {1: 1, 2: 1})
        self.assertTrue(result["summary"]["support_ipv6_static_routing"])
        for secret in ("192.0.2", "2001:db8", "private-route", "private-vrf", "nextHopIp"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_rows_are_partial(self) -> None:
        result = summarize_switch_static_routes([
            {"status": 1, "distance": 256, "destinations": ["bad"] * 17,
             "ipVersion": 9, "resource": 5},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["summary"]["unknown_rows"], 1)
        malformed = summarize_switch_static_routes([
            {"status": True, "distance": 1, "destinations": [None]},
        ])
        self.assertTrue(malformed["partial"])

    def test_rejects_over_limit(self) -> None:
        with self.assertRaises(SwitchStaticRoutesError):
            summarize_switch_static_routes([{}] * 10_001)


if __name__ == "__main__":
    unittest.main()
