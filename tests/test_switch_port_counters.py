from __future__ import annotations

import unittest

from app.switch_port_counters import SwitchPortCountersError, project_switch_port_counters


EXPECTED = "AA-BB-CC-DD-EE-FF"
OTHER = "11:22:33:44:55:66"
I64_MIN, I64_MAX = -(2**63), 2**63 - 1


def row(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "switchMac": "aa:bb:cc:dd:ee:ff",
        "port": 1,
        "txBytes": 0,
        "rxBytes": I64_MAX,
        "txFrames": 2,
        "rxFrames": 3,
        "txMulticast": 4,
        "rxMulticast": 5,
        "txBroadcast": 6,
        "rxBroadcast": 7,
        "txErrors": 8,
        "rxErrors": I64_MIN,
    }
    result.update(overrides)
    return result


class SwitchPortCountersProjectionTests(unittest.TestCase):
    def test_projects_only_matching_switch_and_counter_fields(self) -> None:
        other_row = row(switchMac=OTHER, port=77, switchName="private-other-name",
                        vendorExtra="ignored-other")
        result = project_switch_port_counters([other_row, row()], EXPECTED)
        self.assertEqual(result["data"]["items"], [{
            "port": 1, "txBytes": 0, "rxBytes": I64_MAX,
            "txFrames": 2, "rxFrames": 3, "txMulticast": 4,
            "rxMulticast": 5, "txBroadcast": 6, "rxBroadcast": 7,
            "txErrors": 8, "rxErrors": I64_MIN,
        }])
        self.assertEqual(result["skipped_other_switch_count"], 1)
        self.assertFalse(result["partial"])
        self.assertNotIn(OTHER, repr(result))
        self.assertNotIn("private-other-name", repr(result))

    def test_mac_matching_is_case_and_separator_insensitive(self) -> None:
        result = project_switch_port_counters([row()], "aa:bb:cc:dd:ee:ff")
        self.assertTrue(result["target_rows_present"])
        self.assertFalse(result["partial"])

    def test_expected_mac_must_be_valid(self) -> None:
        for invalid in ("", "aabbccddeeff", "AA-BB:CC-DD-EE-FF", None):
            with self.subTest(invalid=invalid), self.assertRaises(SwitchPortCountersError):
                project_switch_port_counters([], invalid)  # type: ignore[arg-type]

    def test_missing_and_invalid_row_mac_mark_partial_without_disclosure(self) -> None:
        result = project_switch_port_counters([
            {"port": 9, "portName": "private-port"},
            row(switchMac="not-a-mac", switchName="private-switch"),
            row(),
        ], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_row_count"], 2)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual(len(result["data"]["items"]), 1)
        self.assertNotIn("private-port", repr(result))
        self.assertNotIn("private-switch", repr(result))
        self.assertNotIn("not-a-mac", repr(result))

    def test_no_matching_rows_is_partial_unknown_even_if_other_switch_rows_exist(self) -> None:
        result = project_switch_port_counters([row(switchMac=OTHER)], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["items"], [])
        self.assertFalse(result["target_rows_present"])
        self.assertEqual(result["skipped_other_switch_count"], 1)
        result = project_switch_port_counters([], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertFalse(result["target_rows_present"])

    def test_port_range_is_exact_and_bool_is_rejected(self) -> None:
        for port in (0, 4096):
            result = project_switch_port_counters([row(port=port)], EXPECTED)
            self.assertFalse(result["partial"])
            self.assertEqual(result["data"]["items"][0]["port"], port)
        for port in (-1, 4097, True, "1"):
            result = project_switch_port_counters([row(port=port)], EXPECTED)
            self.assertTrue(result["partial"])
            self.assertEqual(result["data"]["items"], [])

    def test_each_counter_requires_strict_int64_without_invented_sign_rule(self) -> None:
        counters = ("txBytes", "rxBytes", "txFrames", "rxFrames", "txMulticast",
                    "rxMulticast", "txBroadcast", "rxBroadcast", "txErrors", "rxErrors")
        for field in counters:
            for value in (I64_MIN, I64_MAX, -1):
                result = project_switch_port_counters([row(**{field: value})], EXPECTED)
                self.assertEqual(result["data"]["items"][0][field], value)
                self.assertFalse(result["partial"])
            for value in (True, I64_MIN - 1, I64_MAX + 1, "12"):
                result = project_switch_port_counters([row(**{field: value})], EXPECTED)
                self.assertTrue(result["partial"])
                self.assertNotIn(field, result["data"]["items"][0])
                self.assertEqual(result["invalid_row_count"], 1)

    def test_missing_counter_field_marks_partial_and_only_safe_values_survive(self) -> None:
        raw = row()
        del raw["txErrors"]
        result = project_switch_port_counters([raw], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_field_count"], 1)
        self.assertNotIn("txErrors", result["data"]["items"][0])

    def test_all_documented_extra_settings_are_redacted_without_partial(self) -> None:
        sensitive = {
            "standardPort": {"unit": 2, "port": 3}, "configStack": True,
            "configMlagPeerLink": True, "configMlagDad": False,
            "stackPortsGroupIndex": 4, "portName": "private-port-name",
            "switchName": "private-switch-name", "switchType": 2,
            "switchStatusCategory": 1, "switchSupportPoe": 1, "site": "private-site",
            "tagIds": ["private-tag-id"], "tagName": "private-tag",
            "connectedStatus": 0, "madUsed": False, "disable": False,
            "type": 1, "operation": "AGGREGATING", "supportPoe": True,
            "poeDisplayType": 4, "poe": 1, "portStatus": {"status": "private"},
            "linkSpeed": 3, "duplex": 2, "lagSetting": {"name": "private-lag"},
            "stackId": "private-stack-id", "stackName": "private-stack-name", "unit": 1,
        }
        result = project_switch_port_counters([row(**sensitive)], EXPECTED)
        self.assertFalse(result["partial"])
        self.assertEqual(result["redacted_field_count"], len(sensitive) + 1)
        rendered = repr(result)
        for secret in ("private-port-name", "private-switch-name", "private-site",
                       "private-tag-id", "private-tag", "private-stack-id",
                       "private-stack-name", "private-lag", "AGGREGATING"):
            self.assertNotIn(secret, rendered)

    def test_unknown_fields_mark_partial_and_do_not_echo_names_or_values(self) -> None:
        result = project_switch_port_counters(
            [row(privateUnknown="private-value")], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("privateUnknown", repr(result))
        self.assertNotIn("private-value", repr(result))

    def test_duplicate_ports_are_kept_and_flagged_not_overwritten(self) -> None:
        result = project_switch_port_counters([row(), row(txBytes=99)], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["duplicate_port_count"], 1)
        self.assertEqual([x["txBytes"] for x in result["data"]["items"]], [0, 99])

    def test_rows_and_fields_are_bounded(self) -> None:
        with self.assertRaises(SwitchPortCountersError):
            project_switch_port_counters([row()] * 4097, EXPECTED)
        oversized_row = project_switch_port_counters(
            [{**row(), **{f"x{i}": i for i in range(54)}}], EXPECTED)
        self.assertTrue(oversized_row["partial"])
        self.assertEqual(oversized_row["data"]["items"], [])
        self.assertEqual(oversized_row["invalid_row_count"], 1)
        with self.assertRaises(SwitchPortCountersError):
            project_switch_port_counters([{**row(), "x" * 129: 1}], EXPECTED)
        with self.assertRaises(SwitchPortCountersError):
            project_switch_port_counters(None, EXPECTED)


if __name__ == "__main__":
    unittest.main()
