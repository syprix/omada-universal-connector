from __future__ import annotations

import unittest

from app.switch_cable_test_results import (
    SwitchCableTestResultsError,
    project_switch_cable_test_results,
)


class SwitchCableTestResultProjectionTests(unittest.TestCase):
    def test_projects_documented_port_states_and_raw_lengths(self) -> None:
        result = project_switch_cable_test_results({
            "status": 0,
            "data": [{"port": 7, "state": [0, 1, 6], "length": [15, 20],
                      "timeStamp": 1700000000000,
                      "standardPort": {"unit": 1, "slot": 2, "port": 7}}],
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"], {
            "status_code": 0,
            "ports": [{"port": 7, "state_codes": [0, 1, 6],
                       "length_values": [15, 20], "timestamp_value": 1700000000000}],
        })
        self.assertNotIn("unit", repr(result))

    def test_unknown_codes_and_missing_fields_are_partial(self) -> None:
        result = project_switch_cable_test_results({
            "status": True,
            "data": [{"port": 2, "state": [9, 2], "length": [2**31], "timeStamp": -1}],
            "stackData": [{"mac": "private-mac"}],
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["ports"], [{"port": 2, "state_codes": [2],
                                                       "length_values": []}])
        self.assertNotIn("private-mac", repr(result))
        self.assertIn("stack_data", result["omitted_fields"])

    def test_invalid_shapes_and_bounds_fail_closed(self) -> None:
        for raw in (None, {"status": 0, "data": [None] * 257},
                    {"status": 0, "data": [{"port": 1, "state": [0] * 17}]},
                    {"status": 0, "data": [], **{f"x{i}": i for i in range(16)}}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(SwitchCableTestResultsError):
                project_switch_cable_test_results(raw)


if __name__ == "__main__":
    unittest.main()
