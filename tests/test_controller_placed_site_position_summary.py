import unittest

from app.controller_placed_site_position_summary import (
    ControllerPlacedSitePositionError,
    MAX_PLACED_SITE_ROWS,
    summarize_placed_site_positions,
)


class ControllerPlacedSitePositionSummaryTests(unittest.TestCase):
    def test_numeric_coordinate_form_counts_only_redacted_coverage(self):
        row = {
            "id": "private-site-id", "region": "private-region", "name": "private-name",
            "longitude": 12.5, "latitude": -7, "address": "private-address",
        }
        result = summarize_placed_site_positions([row])
        self.assertEqual(result["source_state"], "present")
        self.assertEqual(result["placed_site_row_count"], 1)
        self.assertEqual(result["documented_field_count"], 6)
        self.assertEqual(result["documented_field_observed_count"], 6)
        self.assertEqual(result["documented_field_type_valid_count"], 6)
        self.assertEqual(result["rows_with_all_documented_fields_count"], 1)
        self.assertEqual(result["coordinate_number_value_count"], 2)
        self.assertEqual(result["coordinate_object_shape_count"], 0)
        self.assertFalse(result["partial"])
        self.assertFalse(result["server_completeness_established"])
        for private_value in row.values():
            self.assertNotIn(str(private_value), repr(result))

    def test_er_object_coordinate_form_is_counted_without_interpreting_members(self):
        row = {
            "id": "private-site-id", "region": "private-region", "name": "private-name",
            "longitude": {"opaque_coordinate_member": "private-coordinate"},
            "latitude": {"opaque_coordinate_member": "private-coordinate"},
            "address": "private-address",
        }
        result = summarize_placed_site_positions([row])
        self.assertEqual(result["coordinate_number_value_count"], 0)
        self.assertEqual(result["coordinate_object_shape_count"], 2)
        self.assertEqual(result["coordinate_invalid_shape_count"], 0)
        self.assertEqual(result["documented_field_type_valid_count"], 6)
        encoded = repr(result)
        for marker in ("private-site-id", "private-region", "private-name",
                       "private-coordinate", "private-address", "opaque_coordinate_member"):
            self.assertNotIn(marker, encoded)

    def test_empty_missing_and_invalid_result_are_distinct(self):
        empty = summarize_placed_site_positions([])
        missing = summarize_placed_site_positions(None, result_present=False)
        null = summarize_placed_site_positions(None, result_present=True)
        self.assertEqual((empty["source_state"], empty["placed_site_row_count"], empty["empty"]),
                         ("empty", 0, True))
        self.assertEqual((missing["source_state"], missing["placed_site_row_count"], missing["empty"]),
                         ("missing", None, False))
        self.assertEqual((null["source_state"], null["placed_site_row_count"], null["empty"]),
                         ("invalid", None, False))
        self.assertFalse(empty["server_completeness_established"])
        self.assertTrue(missing["partial"] and null["partial"])

    def test_missing_and_invalid_fields_are_counted_without_names_or_values(self):
        result = summarize_placed_site_positions([{
            "id": None, "longitude": True, "latitude": float("inf"),
            "unpublished_field_name": "private-value",
        }])
        self.assertEqual(result["documented_field_presence_count"], 3)
        self.assertEqual(result["documented_field_missing_count"], 3)
        self.assertEqual(result["documented_field_type_invalid_count"], 3)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["coordinate_invalid_shape_count"], 2)
        self.assertTrue(result["partial"])
        self.assertNotIn("unpublished_field_name", repr(result))
        self.assertNotIn("private-value", repr(result))

    def test_invalid_rows_and_bounds_are_explicit(self):
        result = summarize_placed_site_positions([None, {"id": "x" * 5000}])
        self.assertEqual(result["invalid_row_count"], 1)
        self.assertEqual(result["documented_field_type_invalid_count"], 1)
        self.assertTrue(result["partial"])
        large = summarize_placed_site_positions([{}] * (MAX_PLACED_SITE_ROWS + 1))
        self.assertEqual(large["source_state"], "too_large")
        self.assertEqual(large["placed_site_row_count"], MAX_PLACED_SITE_ROWS + 1)
        self.assertTrue(large["partial"])
        with self.assertRaises(ControllerPlacedSitePositionError):
            summarize_placed_site_positions([], result_present=1)


if __name__ == "__main__":
    unittest.main()
