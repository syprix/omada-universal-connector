from __future__ import annotations

import unittest

from app.switch_exist_networks import SwitchExistNetworksError, summarize_switch_exist_networks


class SwitchExistNetworkSummaryTests(unittest.TestCase):
    def test_returns_vlan_type_and_primary_counts_only(self) -> None:
        rows = [
            {"id": "private-id", "name": "Office", "vlan": 20, "vlanType": 0, "primary": True,
             "ip": {"ip": "192.0.2.1"}, "dhcpServer": {"ip": "192.0.2.2"}},
            {"id": "private-id-2", "name": "Guest", "vlan": 20, "vlanType": 1, "primary": False},
        ]
        result = summarize_switch_exist_networks(rows, {"supportMultiVlan": True, "supportRA": False})
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["summary"]["by_vlan"], {20: 2})
        self.assertEqual(result["summary"]["by_vlan_type"], {0: 1, 1: 1})
        self.assertEqual(result["summary"]["primary_count"], 1)
        self.assertEqual(result["summary"]["capabilities"]["supportMultiVlan"], True)
        self.assertNotIn("private-id", repr(result))
        self.assertNotIn("Office", repr(result))
        self.assertNotIn("192.0.2.", repr(result))

    def test_marks_invalid_rows_and_bounds_vlan_values(self) -> None:
        result = summarize_switch_exist_networks([
            {"vlan": 0, "vlanType": True}, {"vlan": 4091}, {},
            {"vlan": 20, "vlanType": 0, "primary": "yes"},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["summary"]["by_vlan"], {20: 1})
        self.assertEqual(result["summary"]["unknown_rows"], 4)

    def test_rejects_over_limit(self) -> None:
        with self.assertRaises(SwitchExistNetworksError):
            summarize_switch_exist_networks([{}] * 4097)


if __name__ == "__main__":
    unittest.main()
