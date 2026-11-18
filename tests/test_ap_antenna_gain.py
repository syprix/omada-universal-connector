from __future__ import annotations

import unittest

from app.ap_antenna_gain import ApAntennaGainError, project_ap_antenna_gain


class ApAntennaGainProjectionTests(unittest.TestCase):
    def test_projects_valid_list_and_preserves_documented_values(self) -> None:
        raw = {"anteGainList": [
            {"radioId": 0, "anteGain": 0},
            {"radioId": 3, "anteGain": 30},
        ]}
        result = project_ap_antenna_gain(raw)
        self.assertEqual(result, {
            "status": "ok", "resource": "ap_antenna_gain", "data": raw,
            "partial": False, "missing_fields": [], "invalid_fields": [],
            "unknown_field_count": 0, "invalid_item_count": 0,
            "duplicate_radio_id_count": 0,
        })

    def test_empty_list_is_preserved_as_observed(self) -> None:
        result = project_ap_antenna_gain({"anteGainList": []})
        self.assertEqual(result["data"], {"anteGainList": []})
        self.assertFalse(result["partial"])

    def test_missing_list_and_item_fields_are_partial(self) -> None:
        missing_list = project_ap_antenna_gain({})
        self.assertEqual(missing_list["missing_fields"], ["anteGainList"])
        self.assertTrue(missing_list["partial"])

        missing_item_fields = project_ap_antenna_gain({"anteGainList": [{"radioId": 1}]})
        self.assertEqual(missing_item_fields["data"], {"anteGainList": [{"radioId": 1}]})
        self.assertEqual(missing_item_fields["missing_fields"], ["anteGainList[].anteGain"])
        self.assertTrue(missing_item_fields["partial"])

    def test_bool_invalid_types_and_out_of_range_values_are_partial(self) -> None:
        cases = (
            {"radioId": True, "anteGain": 10},
            {"radioId": 4, "anteGain": 10},
            {"radioId": 1, "anteGain": -1},
            {"radioId": 2, "anteGain": 31},
            {"radioId": 1.0, "anteGain": 10},
            {"radioId": 2, "anteGain": False},
        )
        for item in cases:
            with self.subTest(item=item):
                result = project_ap_antenna_gain({"anteGainList": [item]})
                self.assertTrue(result["partial"])
                self.assertTrue(result["invalid_fields"])
                self.assertEqual(len(result["data"]["anteGainList"]), 1)
                projected = result["data"]["anteGainList"][0]
                for field, low, high in (("radioId", 0, 3), ("anteGain", 0, 30)):
                    value = item[field]
                    valid = type(value) is int and low <= value <= high
                    self.assertEqual(field in projected, valid)

    def test_duplicate_radio_ids_are_kept_and_explicitly_marked_partial(self) -> None:
        raw = {"anteGainList": [
            {"radioId": 2, "anteGain": 7},
            {"radioId": 2, "anteGain": 9},
        ]}
        result = project_ap_antenna_gain(raw)
        self.assertEqual(result["data"]["anteGainList"], raw["anteGainList"])
        self.assertEqual(result["duplicate_radio_id_count"], 1)
        self.assertTrue(result["partial"])

    def test_unknown_fields_and_invalid_rows_are_redacted(self) -> None:
        raw = {"anteGainList": [
            {"radioId": 0, "anteGain": 2, "deviceName": "private-ap"},
            "private raw entry",
        ], "privateTop": "private-value"}
        result = project_ap_antenna_gain(raw)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertEqual(result["invalid_item_count"], 1)
        self.assertTrue(result["partial"])
        rendered = repr(result)
        for secret in ("deviceName", "private-ap", "private raw entry", "privateTop", "private-value"):
            self.assertNotIn(secret, rendered)

    def test_bounds_top_level_list_and_nested_objects(self) -> None:
        for raw in (None, [], "not-an-object", {f"unknown-{i}": i for i in range(9)},
                    {"x" * 129: []}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ApAntennaGainError):
                project_ap_antenna_gain(raw)
        for raw in (
            {"anteGainList": [{} for _ in range(65)]},
            {"anteGainList": [{f"extra-{i}": i for i in range(9)}]},
            {"anteGainList": [{"x" * 129: 1}]},
        ):
            with self.subTest(size=repr(raw)[:24]), self.assertRaises(ApAntennaGainError):
                project_ap_antenna_gain(raw)


if __name__ == "__main__":
    unittest.main()
