from __future__ import annotations

import unittest

from app.switch_networks import SwitchNetworksError, summarize_switch_networks


class SwitchNetworkSummaryTests(unittest.TestCase):
    def test_returns_only_vlan_and_documented_mode_status_counts(self) -> None:
        rows = [
            {"id": "private-id", "name": "Office", "vlan": 20, "status": 1, "mode": 1,
             "ip": {"ip": "192.0.2.1"}, "dhcpServer": {"ip": "192.0.2.2"}},
            {"id": "private-id-2", "name": "Guest", "vlan": 20, "status": 0, "mode": 2,
             "ipv6": {"ipv6Addr": "2001:db8::1"}},
        ]
        result = summarize_switch_networks(rows)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["summary"]["by_vlan"], {20: 2})
        self.assertEqual(result["summary"]["by_status_code"], {0: 1, 1: 1})
        self.assertEqual(result["summary"]["by_dhcp_mode_code"], {1: 1, 2: 1})
        self.assertFalse(result["partial"])
        for secret in ("private-id", "Office", "Guest", "192.0.2.", "2001:db8"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_codes_are_partial_and_bounded(self) -> None:
        result = summarize_switch_networks([{"vlan": True, "status": 4, "mode": 99},
                                             {"vlan": 10**20, "status": 1, "mode": 0}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["summary"]["unknown_rows"], 2)
        self.assertEqual(result["summary"]["by_status_code"], {1: 1})

    def test_rejects_over_limit(self) -> None:
        with self.assertRaises(SwitchNetworksError):
            summarize_switch_networks([{}] * 10_001)


if __name__ == "__main__":
    unittest.main()
