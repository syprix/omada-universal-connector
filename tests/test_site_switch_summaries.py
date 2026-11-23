from __future__ import annotations

import unittest

from app.site_switch_ddm_summary import summarize_switch_ddm_rows
from app.site_switch_qos_summary import summarize_switch_qos_rules


class SiteSwitchProjectionTests(unittest.TestCase):
    def test_qos_counts_documented_type_state_and_queue_without_rule_details(self):
        result = summarize_switch_qos_rules([
            {"name": "private rule", "id": "private-id", "type": 2,
             "status": True, "queue": 7, "sPort": 443, "dPort": 8443,
             "ipVersion": [0, 1], "dscp": 42},
            {"type": 0, "status": False, "queue": 0}], 2, 0)
        self.assertEqual(result["by_documented_rule_type"]["custom"], 1)
        self.assertEqual(result["reported_rule_status"]["enabled"], 1)
        self.assertEqual(result["by_documented_queue"]["7"], 1)
        for secret in ("private rule", "private-id", "443", "8443", "42"):
            self.assertNotIn(secret, repr(result))
        self.assertFalse(result["traffic_behavior_inferred"])

    def test_qos_invalid_and_missing_values_are_distinct(self):
        result = summarize_switch_qos_rules(
            [{"type": 9, "status": "on", "queue": 8}, {"type": 0}], 2, 0)
        self.assertEqual(result["by_documented_queue"]["invalid"], 1)
        self.assertEqual(result["by_documented_queue"]["missing"], 1)
        self.assertEqual(result["reported_rule_status"]["unknown"], 1)
        self.assertEqual(result["reported_rule_status"]["missing"], 1)
        self.assertEqual(result["status"], "partial")

    def test_ddm_counts_only_documented_flags_and_omits_ports_and_measurements(self):
        result = summarize_switch_ddm_rows([
            {"port": 4, "standardPort": "1/0/4", "rxPower": 0.42,
             "dataReady": 1, "transmitFault": 0, "lossOfSignal": 1,
             "temperature": 45.5},
            {"dataReady": 0, "transmitFault": 1, "lossOfSignal": 0}])
        self.assertEqual(result["reported_controller_flags"]["dataReady"]["valid"], 1)
        self.assertEqual(result["reported_controller_flags"]["dataReady"]["invalid"], 1)
        self.assertEqual(result["reported_controller_flags"]["transmitFault"]["reported_fault"], 1)
        self.assertEqual(result["reported_controller_flags"]["lossOfSignal"]["reported_loss"], 1)
        for secret in ("1/0/4", "0.42", "45.5", '"port"'):
            self.assertNotIn(secret, repr(result))
        self.assertFalse(result["device_health_inferred"])

    def test_ddm_missing_and_invalid_flags_remain_distinct(self):
        result = summarize_switch_ddm_rows([
            {"dataReady": 2, "transmitFault": "yes"}, {}])
        self.assertEqual(result["reported_controller_flags"]["dataReady"]["unknown"], 1)
        self.assertEqual(result["reported_controller_flags"]["transmitFault"]["invalid"], 1)
        self.assertEqual(result["reported_controller_flags"]["lossOfSignal"]["missing"], 2)
        self.assertEqual(result["status"], "partial")


if __name__ == "__main__":
    unittest.main()
