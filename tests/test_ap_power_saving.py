from __future__ import annotations

import unittest

from app.ap_power_saving import ApPowerSavingError, project_ap_power_saving


INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


def complete_result() -> dict[str, object]:
    return {
        "mode": 3,
        "timeEnable": True,
        "bandEnable": False,
        "supportPowerSaving": True,
        "startTimeH": 0,
        "endTimeH": 23,
        "startTimeM": 0,
        "endTimeM": 59,
        "bands": [0, 1, 2, 3],
        "idleDuration": INT32_MIN,
    }


class ApPowerSavingProjectionTests(unittest.TestCase):
    def test_projects_documented_values_without_interpretation(self) -> None:
        raw = complete_result()
        result = project_ap_power_saving(raw)
        self.assertEqual(result, {
            "status": "ok", "resource": "ap_power_saving", "data": raw,
            "partial": False, "missing_fields": [], "invalid_fields": [],
            "unknown_field_count": 0, "duplicate_band_count": 0,
        })

    def test_missing_mode_is_partial_for_er_family_and_not_invented(self) -> None:
        raw = complete_result()
        del raw["mode"]
        result = project_ap_power_saving(raw)
        self.assertNotIn("mode", result["data"])
        self.assertEqual(result["missing_fields"], ["mode"])
        self.assertTrue(result["partial"])

    def test_documented_hour_minute_and_mode_ranges_are_inclusive(self) -> None:
        self.assertFalse(project_ap_power_saving(complete_result())["partial"])
        for field, value in (("mode", -1), ("mode", 4),
                             ("startTimeH", -1), ("endTimeH", 24),
                             ("startTimeM", -1), ("endTimeM", 60)):
            with self.subTest(field=field, value=value):
                raw = complete_result()
                raw[field] = value
                result = project_ap_power_saving(raw)
                self.assertIn(field, result["invalid_fields"])
                self.assertNotIn(field, result["data"])
                self.assertTrue(result["partial"])

    def test_bool_fields_reject_integer_substitutes(self) -> None:
        for field in ("timeEnable", "bandEnable", "supportPowerSaving"):
            with self.subTest(field=field):
                raw = complete_result()
                raw[field] = 1
                result = project_ap_power_saving(raw)
                self.assertIn(field, result["invalid_fields"])
                self.assertNotIn(field, result["data"])
                self.assertTrue(result["partial"])

    def test_bands_allow_only_unique_integer_ids_and_preserve_duplicates(self) -> None:
        raw = complete_result()
        raw["bands"] = [3, 1, 1, True, 9]
        result = project_ap_power_saving(raw)
        self.assertEqual(result["data"]["bands"], [3, 1, 1])
        self.assertEqual(result["duplicate_band_count"], 1)
        self.assertEqual(result["invalid_fields"], ["bands[]", "bands[]"])
        self.assertTrue(result["partial"])

    def test_idle_duration_accepts_any_int32_and_rejects_bool_or_out_of_int32(self) -> None:
        for value in (INT32_MIN, INT32_MAX, -1000000):
            with self.subTest(value=value):
                raw = complete_result()
                raw["idleDuration"] = value
                result = project_ap_power_saving(raw)
                self.assertEqual(result["data"]["idleDuration"], value)
                self.assertFalse(result["partial"])
        for value in (True, INT32_MAX + 1, INT32_MIN - 1):
            raw = complete_result()
            raw["idleDuration"] = value
            result = project_ap_power_saving(raw)
            self.assertIn("idleDuration", result["invalid_fields"])
            self.assertTrue(result["partial"])

    def test_unknown_fields_mark_partial_without_disclosing_raw_values(self) -> None:
        raw = complete_result()
        raw["privateField"] = "private-ap-name"
        raw["isEffective"] = True
        result = project_ap_power_saving(raw)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertTrue(result["partial"])
        for secret in ("privateField", "private-ap-name", "isEffective"):
            self.assertNotIn(secret, repr(result))

    def test_bounds_root_and_band_list(self) -> None:
        for raw in (None, [], "raw", {f"extra{i}": i for i in range(17)},
                    {"x" * 129: 1}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ApPowerSavingError):
                project_ap_power_saving(raw)
        raw = complete_result()
        raw["bands"] = list(range(17))
        with self.assertRaises(ApPowerSavingError):
            project_ap_power_saving(raw)


if __name__ == "__main__":
    unittest.main()
