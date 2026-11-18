from __future__ import annotations

import unittest

from app.switch_interfaces import SwitchInterfacesError, summarize_switch_interfaces


class SwitchInterfaceSummaryTests(unittest.TestCase):
    def test_counts_only_documented_interface_types(self) -> None:
        rows = [{"type": 0, "id": "private-id", "interfaceId": 9, "name": "Loopback9"},
                {"type": 1, "id": "private-vlan", "interfaceId": 20, "name": "VLAN20"},
                {"type": 1, "id": "private-vlan-2", "interfaceId": 30}]
        result = summarize_switch_interfaces(rows)
        self.assertEqual(result["summary"]["by_type_code"], {0: 1, 1: 2})
        self.assertEqual(result["count"], 3)
        self.assertFalse(result["partial"])
        for secret in ("private-id", "private-vlan", "Loopback9", "VLAN20", "interfaceId"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_or_missing_type_is_counted_as_unknown(self) -> None:
        result = summarize_switch_interfaces([{"type": True}, {}, {"type": 2}])
        self.assertEqual(result["summary"], {"by_type_code": {}, "unknown_rows": 3})
        self.assertTrue(result["partial"])

    def test_rejects_over_limit(self) -> None:
        with self.assertRaises(SwitchInterfacesError):
            summarize_switch_interfaces([{}] * 4097)


if __name__ == "__main__":
    unittest.main()
