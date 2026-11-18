from __future__ import annotations

import unittest

from app.switch_port_poe_info import SwitchPortPoeInfoError, project_switch_port_poe_info


EXPECTED = "AA-BB-CC-DD-EE-FF"
OTHER = "11:22:33:44:55:66"


def row(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "switchMac": "aa:bb:cc:dd:ee:ff", "port": 1,
        "supportPoe": True, "poeDisplayType": 4, "poe": 1,
        "poeStatus": 1.0, "power": 10.0, "voltage": 52.0, "current": 0.2,
    }
    value.update(overrides)
    return value


class SwitchPortPoeInfoProjectionTests(unittest.TestCase):
    def test_projects_only_allowed_values_for_expected_switch(self) -> None:
        result = project_switch_port_poe_info([row(
            supportPoe=True, poeDisplayType=4, poe=1,
            poeStatus=0.25, power=5, voltage=52.1, current=0.2)], EXPECTED)
        self.assertEqual(result["data"]["items"], [{
            "port": 1, "supportPoe": True, "poeDisplayType": 4, "poe": 1,
            "poeStatus": 0.25, "power": 5, "voltage": 52.1, "current": 0.2,
        }])
        self.assertFalse(result["partial"])

    def test_valid_rows_for_other_switch_are_skipped_without_echo(self) -> None:
        result = project_switch_port_poe_info([
            row(switchMac=OTHER, port=99, switchName="private-switch", pdClass="private-pd")], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["items"], [])
        self.assertEqual(result["skipped_other_switch_count"], 1)
        self.assertFalse(result["target_rows_present"])
        self.assertNotIn(OTHER, repr(result))
        self.assertNotIn("private-switch", repr(result))

    def test_expected_mac_is_validated_and_format_normalized(self) -> None:
        self.assertFalse(project_switch_port_poe_info([row()], "aa:bb:cc:dd:ee:ff")["partial"])
        for invalid in ("", "AABBCCDDEEFF", "AA-BB:CC-DD-EE-FF", None):
            with self.subTest(invalid=invalid), self.assertRaises(SwitchPortPoeInfoError):
                project_switch_port_poe_info([], invalid)  # type: ignore[arg-type]

    def test_missing_or_invalid_row_mac_marks_partial_and_omits_row(self) -> None:
        result = project_switch_port_poe_info([
            {"port": 2}, row(switchMac="not-a-mac", port=3), row()], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_row_count"], 2)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual([item["port"] for item in result["data"]["items"]], [1])
        self.assertNotIn("not-a-mac", repr(result))

    def test_port_requires_bounded_non_bool_integer(self) -> None:
        for port in (0, 4096):
            result = project_switch_port_poe_info([row(port=port)], EXPECTED)
            self.assertEqual(result["data"]["items"][0]["port"], port)
            self.assertFalse(result["partial"])
        for port in (-1, 4097, True, "1"):
            result = project_switch_port_poe_info([row(port=port)], EXPECTED)
            self.assertTrue(result["partial"])
            self.assertEqual(result["data"]["items"], [])

    def test_documented_poe_values_are_strictly_validated(self) -> None:
        for value in (True, False):
            self.assertEqual(project_switch_port_poe_info(
                [row(supportPoe=value)], EXPECTED)["data"]["items"][0]["supportPoe"], value)
        for value in (-1, 0, 9):
            self.assertEqual(project_switch_port_poe_info(
                [row(poeDisplayType=value)], EXPECTED)["data"]["items"][0]["poeDisplayType"], value)
        for value in (0, 1):
            self.assertEqual(project_switch_port_poe_info(
                [row(poe=value)], EXPECTED)["data"]["items"][0]["poe"], value)
        for field, bad_values in (
            ("supportPoe", (0, 1, "true")),
            ("poeDisplayType", (-2, 10, True)),
            ("poe", (-1, 2, True)),
        ):
            for value in bad_values:
                with self.subTest(field=field, value=value):
                    result = project_switch_port_poe_info([row(**{field: value})], EXPECTED)
                    self.assertTrue(result["partial"])
                    self.assertNotIn(field, result["data"]["items"][0])

    def test_numeric_measurements_are_finite_and_have_no_unit_interpretation(self) -> None:
        for field in ("poeStatus", "power", "voltage", "current"):
            for value in (-2, 0.0, 52.5):
                result = project_switch_port_poe_info([row(**{field: value})], EXPECTED)
                self.assertEqual(result["data"]["items"][0][field], value)
                self.assertFalse(result["partial"])
            for value in (True, "1.5", float("nan"), float("inf"), 10**1000):
                result = project_switch_port_poe_info([row(**{field: value})], EXPECTED)
                self.assertTrue(result["partial"])
                self.assertNotIn(field, result["data"]["items"][0])
                self.assertEqual(result["invalid_row_count"], 1)

    def test_missing_optional_poe_values_mark_partial_without_inventing_values(self) -> None:
        result = project_switch_port_poe_info(
            [{"switchMac": "aa:bb:cc:dd:ee:ff", "port": 1}], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_field_count"], 7)
        self.assertEqual(result["data"]["items"], [{"port": 1}])
        source = row()
        del source["power"]
        result = project_switch_port_poe_info([source], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_field_count"], 1)
        self.assertNotIn("power", result["data"]["items"][0])

    def test_documented_settings_and_pdclass_are_redacted(self) -> None:
        private_fields = {
            "standardPort": {"port": 2}, "configStack": True,
            "configMlagPeerLink": False, "configMlagDad": True,
            "stackPortsGroupIndex": 3, "portName": "private-port",
            "switchName": "private-switch", "switchType": 1,
            "switchStatusCategory": 1, "switchSupportPoe": 1,
            "site": "private-site", "tagIds": ["private-tag-id"],
            "tagName": "private-tag", "connectedStatus": 0, "madUsed": False,
            "disable": False, "type": 1, "operation": "SWITCHING",
            "portStatus": {"private": "nested"}, "linkSpeed": 3,
            "duplex": 2, "lagSetting": {"private": True}, "stackId": "private-stack",
            "stackName": "private-stack-name", "unit": 1, "pdClass": "private-pd-class",
        }
        result = project_switch_port_poe_info([row(**private_fields)], EXPECTED)
        self.assertFalse(result["partial"])
        self.assertEqual(result["redacted_field_count"], len(private_fields) + 1)
        rendered = repr(result)
        for private in ("private-port", "private-switch", "private-site", "private-tag-id",
                        "private-tag", "SWITCHING", "private-stack", "private-stack-name",
                        "private-pd-class", "nested"):
            self.assertNotIn(private, rendered)

    def test_unknown_fields_partial_and_no_target_rows_are_unknown(self) -> None:
        result = project_switch_port_poe_info([row(unknownExtra="private-extra")], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("unknownExtra", repr(result))
        self.assertNotIn("private-extra", repr(result))
        empty = project_switch_port_poe_info([], EXPECTED)
        self.assertTrue(empty["partial"])
        self.assertFalse(empty["target_rows_present"])

    def test_duplicates_and_bounds(self) -> None:
        result = project_switch_port_poe_info([row(), row(power=3)], EXPECTED)
        self.assertTrue(result["partial"])
        self.assertEqual(result["duplicate_port_count"], 1)
        self.assertEqual([x["port"] for x in result["data"]["items"]], [1, 1])
        with self.assertRaises(SwitchPortPoeInfoError):
            project_switch_port_poe_info([row()] * 4097, EXPECTED)
        oversized = project_switch_port_poe_info(
            [{**row(), **{f"x{i}": i for i in range(63)}}], EXPECTED)
        self.assertTrue(oversized["partial"])
        self.assertEqual(oversized["data"]["items"], [])
        with self.assertRaises(SwitchPortPoeInfoError):
            project_switch_port_poe_info([{**row(), "x" * 129: 1}], EXPECTED)
        with self.assertRaises(SwitchPortPoeInfoError):
            project_switch_port_poe_info(None, EXPECTED)


if __name__ == "__main__":
    unittest.main()
