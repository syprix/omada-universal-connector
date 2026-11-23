from __future__ import annotations

import unittest

from app.site_lan_interface_isolation_summary import summarize_lan_interface_isolation
from app.site_ospf_interface_summary import summarize_ospf_interfaces


class SiteLanOspfProjectionTests(unittest.TestCase):
    def test_lan_isolation_counts_only_typed_flags_and_omits_values(self):
        result = summarize_lan_interface_isolation([
            {"name": "private LAN", "id": "private-id", "vlan": 12, "isolation": True},
            {"isolation": False}, {"isolation": None}, {},
        ])
        self.assertEqual(result["reported_isolation"], {
            "isolated": 1, "not_isolated": 1, "unknown": 1, "missing": 1})
        self.assertEqual(result["status"], "partial")
        self.assertNotIn("private LAN", repr(result))
        self.assertNotIn("private-id", repr(result))
        self.assertNotIn("12", repr(result))
        self.assertFalse(result["network_separation_inferred"])

    def test_ospf_counts_documented_values_and_omits_keys_and_identifiers(self):
        result = summarize_ospf_interfaces([
            {"type": 1, "networkType": 3, "cost": 65535,
             "passiveEnable": True, "deadInterval": 40,
             "loopbackId": 5, "loopbackInterfaceId": "private-loopback",
             "stackId": "private-stack", "simpleKey": "private-key",
             "md5Key": "private-md5", "deviceName": "private-device",
             "mac": "00:11:22:33:44:55", "vlanId": 12}],
            1, 0)
        self.assertEqual(result["by_documented_interface_type"]["loopback"], 1)
        self.assertEqual(result["by_documented_network_type"]["point_to_point"], 1)
        self.assertEqual(result["reported_link_cost_range"]["valid"], 1)
        for secret in ("private-loopback", "private-stack", "private-key", "private-md5",
                       "private-device", "00:11:22:33:44:55", "12"):
            self.assertNotIn(secret, repr(result))
        self.assertFalse(result["ospf_neighbor_state_inferred"])

    def test_ospf_unavailable_optional_values_are_reported_as_missing(self):
        result = summarize_ospf_interfaces(
            [{"networkType": 99, "cost": 65_536}], 1, 0)
        self.assertEqual(result["by_documented_interface_type"]["missing"], 1)
        self.assertEqual(result["by_documented_network_type"]["unknown"], 1)
        self.assertEqual(result["reported_link_cost_range"]["invalid"], 1)
        self.assertEqual(result["reported_optional_field_coverage"]["passiveEnable"]["missing"], 1)
        self.assertEqual(result["status"], "partial")


if __name__ == "__main__":
    unittest.main()
