from __future__ import annotations

import unittest

from app.switch_vlan_interfaces import (
    SwitchVlanInterfacesError,
    summarize_switch_vlan_interfaces,
)


class SwitchVlanInterfaceSummaryTests(unittest.TestCase):
    def test_counts_rows_and_distinct_vlan_ids_without_exposing_source_fields(self) -> None:
        rows = [
            {"vlanInterfaceId": "private-id-1", "vlanInterfaceName": "private-name-1",
             "vlanId": 20},
            {"vlanInterfaceId": "private-id-2", "vlanInterfaceName": "private-name-2",
             "vlanId": 20},
            {"vlanInterfaceId": "private-id-3", "vlanInterfaceName": "private-name-3",
             "vlanId": 30},
        ]
        result = summarize_switch_vlan_interfaces(rows)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["summary"], {"unique_vlan_count": 2, "unknown_rows": 0})
        for private_value in ("private-id-1", "private-name-1", "vlanInterfaceId",
                              "vlanInterfaceName", '"vlanId"', "20", "30"):
            self.assertNotIn(private_value, repr(result))

    def test_counts_missing_and_invalid_vlan_ids_as_unknown(self) -> None:
        result = summarize_switch_vlan_interfaces([
            {"vlanId": True}, {}, {"vlanId": 2**31}, None,
        ])
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["summary"], {"unique_vlan_count": 0, "unknown_rows": 4})
        self.assertTrue(result["partial"])

    def test_rejects_over_limit(self) -> None:
        with self.assertRaises(SwitchVlanInterfacesError):
            summarize_switch_vlan_interfaces([{}] * 4097)


if __name__ == "__main__":
    unittest.main()
