from __future__ import annotations

import unittest

from app.ap_antenna import ApAntennaError, project_ap_antenna


BANDS = ("2g", "5g", "5g2", "6g")
SETTING_FIELDS = ("antMode", "antGain", "antPattern", "customGainLimit", "defaultOmniGain")
INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


def complete_result() -> dict[str, object]:
    result: dict[str, object] = {"antMode": 3, "omniAntState": 2}
    for index, band in enumerate(BANDS):
        result[f"antSetting{band}"] = {
            "antMode": index,
            "antGain": 5,
            "antPattern": index % 2,
            "customGainLimit": 9,
            "defaultOmniGain": 3,
        }
    return result


class ApAntennaProjectionTests(unittest.TestCase):
    def test_projects_documented_global_and_per_band_fields(self) -> None:
        raw = complete_result()
        result = project_ap_antenna(raw)
        self.assertEqual(result, {
            "status": "ok", "resource": "ap_antenna", "data": raw,
            "partial": False, "missing_fields": [], "invalid_fields": [],
            "unknown_field_count": 0,
        })

    def test_global_enums_are_strict_and_bool_is_not_integer(self) -> None:
        for field, values in (("antMode", (-1, 4, True, 1.0)),
                              ("omniAntState", (-1, 3, False, 2.0))):
            for value in values:
                with self.subTest(field=field, value=value):
                    raw = complete_result()
                    raw[field] = value
                    result = project_ap_antenna(raw)
                    self.assertIn(field, result["invalid_fields"])
                    self.assertNotIn(field, result["data"])
                    self.assertTrue(result["partial"])

    def test_nested_int32_fields_have_no_extra_range_except_ant_pattern(self) -> None:
        raw = complete_result()
        raw["antSetting2g"] = {
            "antMode": INT32_MIN,
            "antGain": INT32_MAX,
            "antPattern": 1,
            "customGainLimit": INT32_MIN,
            "defaultOmniGain": INT32_MAX,
        }
        result = project_ap_antenna(raw)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["antSetting2g"], raw["antSetting2g"])

    def test_nested_values_reject_bool_out_of_int32_and_invalid_pattern(self) -> None:
        cases = (("antMode", True), ("antGain", INT32_MAX + 1),
                 ("antPattern", -1), ("customGainLimit", False),
                 ("defaultOmniGain", INT32_MIN - 1))
        for field, value in cases:
            with self.subTest(field=field, value=value):
                raw = complete_result()
                raw["antSetting5g2"][field] = value
                result = project_ap_antenna(raw)
                self.assertIn(f"antSetting5g2.{field}", result["invalid_fields"])
                self.assertNotIn(field, result["data"]["antSetting5g2"])
                self.assertTrue(result["partial"])

    def test_missing_objects_and_nested_fields_are_partial_without_defaults(self) -> None:
        raw = complete_result()
        del raw["antSetting6g"]
        del raw["antSetting2g"]["defaultOmniGain"]
        result = project_ap_antenna(raw)
        self.assertNotIn("antSetting6g", result["data"])
        self.assertNotIn("defaultOmniGain", result["data"]["antSetting2g"])
        self.assertIn("antSetting6g", result["missing_fields"])
        self.assertIn("antSetting2g.defaultOmniGain", result["missing_fields"])
        self.assertTrue(result["partial"])

    def test_wrong_nested_container_and_unknown_fields_are_partial_and_redacted(self) -> None:
        raw = complete_result()
        raw["antSetting2g"] = "private raw antenna settings"
        raw["antSetting5g"]["secretName"] = "private-ap-name"
        raw["unknownTop"] = {"secret": "private-value"}
        result = project_ap_antenna(raw)
        self.assertIn("antSetting2g", result["invalid_fields"])
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertTrue(result["partial"])
        rendered = repr(result)
        for secret in ("private raw antenna settings", "secretName", "private-ap-name",
                       "unknownTop", "private-value"):
            self.assertNotIn(secret, rendered)

    def test_bounds_objects_and_does_not_invent_5g1(self) -> None:
        for raw in (None, [], "raw", {f"unknown{i}": i for i in range(17)},
                    {"x" * 129: 1}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ApAntennaError):
                project_ap_antenna(raw)
        raw = complete_result()
        raw["antSetting2g"].update({f"unknown{i}": i for i in range(12)})
        with self.assertRaises(ApAntennaError):
            project_ap_antenna(raw)
        valid = project_ap_antenna(complete_result())
        self.assertNotIn("antSetting5g1", valid["data"])


if __name__ == "__main__":
    unittest.main()
