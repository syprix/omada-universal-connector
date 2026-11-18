from __future__ import annotations

import unittest

from app.switch_cable_test_logs import (
    SwitchCableTestLogsError,
    project_switch_cable_test_logs,
)


def log(**overrides):
    row = {"type": 0, "timeStamp": 1700000000000, "testPortList": [],
           "completePortList": [], "cancelPortList": [], "timeoutPortList": []}
    row.update(overrides)
    return row


class SwitchCableTestLogProjectionTests(unittest.TestCase):
    def test_keeps_only_documented_codes_times_and_flat_port_numbers(self) -> None:
        result = project_switch_cable_test_logs([log(
            testPortList=[{"port": 5, "standardPort": {"unit": 1, "slot": 2, "port": 5}}],
            completePortList=[{"port": 5}], extra="private")])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["data"]["logs"], [{
            "type_code": 0, "timestamp_value": 1700000000000,
            "test_ports": [5], "complete_ports": [5], "cancelled_ports": [],
            "timed_out_ports": [],
        }])
        self.assertTrue(result["partial"])
        for forbidden in ("unit", "slot", "private", "extra"):
            self.assertNotIn(forbidden, repr(result))

    def test_missing_and_invalid_values_are_partial(self) -> None:
        result = project_switch_cable_test_logs([{
            "type": True, "timeStamp": -1, "testPortList": [None],
            "completePortList": "invalid", "cancelPortList": [],
        }])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["logs"], [{
            "test_ports": [], "cancelled_ports": [],
        }])
        self.assertIn("logs[0].timeoutPortList", result["missing_fields"])

    def test_bounds_and_root_type_fail_closed(self) -> None:
        for raw in (None, {"logs": []}, [log()] * 65,
                    [log(testPortList=[{"port": 1}] * 129)]):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(SwitchCableTestLogsError):
                project_switch_cable_test_logs(raw)


if __name__ == "__main__":
    unittest.main()
