from __future__ import annotations

import unittest

from app.switch_port_networks import SwitchPortNetworksError, summarize_switch_port_networks


class SwitchPortNetworkSummaryTests(unittest.TestCase):
    def test_counts_by_vlan_and_omits_network_identifiers_and_names(self) -> None:
        result = summarize_switch_port_networks([
            {"id": "private-network-1", "name": "Office", "vlan": 20},
            {"id": "private-network-2", "name": "Guest", "vlan": 30},
            {"id": "private-network-3", "name": "Another", "vlan": 20},
        ])
        self.assertEqual(result["summary"]["vlans"], [
            {"vlan_id": 20, "network_count": 2},
            {"vlan_id": 30, "network_count": 1},
        ])
        for secret in ("private-network", "Office", "Guest", "Another"):
            self.assertNotIn(secret, repr(result))

    def test_unknown_vlan_values_are_counted(self) -> None:
        result = summarize_switch_port_networks([{"vlan": 0}, {"vlan": True}, {}])
        self.assertEqual(result["summary"]["vlans"], [{"vlan_id": 0, "network_count": 1}])
        self.assertEqual(result["summary"]["unknown_vlan_rows"], 2)
        self.assertTrue(result["partial"])

    def test_row_limit_fails_closed(self) -> None:
        with self.assertRaises(SwitchPortNetworksError):
            summarize_switch_port_networks([{}] * 10_001)


if __name__ == "__main__":
    unittest.main()
