import unittest

from app.controller_unplaced_site_position_summary import (
    PAGE_SIZE,
    ControllerUnplacedSitePositionError,
    project_unplaced_site_positions,
)


def page(rows, *, total=1, unplaced=1, current_size=None):
    return {
        "totalRows": total,
        "currentPage": 1,
        "currentSize": len(rows) if current_size is None else current_size,
        "data": rows,
        "unplacedNum": unplaced,
    }


class ControllerUnplacedSitePositionSummaryTests(unittest.TestCase):
    def test_documented_rows_are_counted_without_returning_site_values(self):
        row = {"id": "private-id", "region": "private-region",
               "name": "private-name", "type": 4}
        result = project_unplaced_site_positions(page([row]))
        self.assertEqual(result["source_state"], "present")
        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(result["reported_total_rows"], 1)
        self.assertEqual(result["reported_unplaced_num"], 1)
        self.assertFalse(result["partial"])
        self.assertEqual(result["documented_field_coverage"]["id"],
                         {"present": 1, "type_valid": 1, "missing": 0, "invalid": 0})
        encoded = repr(result)
        for value in row.values():
            self.assertNotIn(str(value), encoded)

    def test_empty_and_unreported_counters_are_explicit_and_partial(self):
        empty = project_unplaced_site_positions(page([], total=0, unplaced=0, current_size=PAGE_SIZE))
        self.assertEqual(empty["source_state"], "empty")
        self.assertEqual(empty["returned_count"], 0)
        self.assertEqual(empty["page_coverage_state"], "complete_as_reported")
        self.assertFalse(empty["partial"])
        missing = project_unplaced_site_positions({
            "currentPage": 1, "currentSize": 100, "data": [],
        })
        self.assertEqual(missing["total_rows_state"], "not_reported")
        self.assertEqual(missing["unplaced_num_state"], "not_reported")
        self.assertIsNone(missing["omitted_count"])
        self.assertEqual(missing["page_coverage_state"], "unknown_total")
        self.assertTrue(missing["partial"])

    def test_total_rows_truncation_and_unplaced_num_are_separate_counts(self):
        rows = [{"id": "a", "region": "r", "name": "n", "type": -3}]
        result = project_unplaced_site_positions(page(rows, total=3, unplaced=9))
        self.assertEqual(result["reported_total_rows"], 3)
        self.assertEqual(result["reported_unplaced_num"], 9)
        self.assertEqual(result["omitted_count"], 2)
        self.assertEqual(result["page_coverage_state"], "truncated")
        self.assertTrue(result["page_truncated"])
        self.assertTrue(result["partial"])

    def test_missing_invalid_and_unknown_row_fields_are_only_aggregated(self):
        result = project_unplaced_site_positions(page([
            {"id": None, "region": "r", "name": "n", "type": True,
             "private_unknown_field": "private-value"},
        ]))
        self.assertEqual(result["documented_field_coverage"]["id"]["invalid"], 1)
        self.assertEqual(result["documented_field_coverage"]["type"]["invalid"], 1)
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["unknown_row_field_count"], 1)
        self.assertTrue(result["partial"])
        for private in ("private_unknown_field", "private-value"):
            self.assertNotIn(private, repr(result))

    def test_counter_types_ranges_and_page_shapes_are_strict(self):
        good = page([{"id": "x", "region": "r", "name": "n", "type": 0}])
        for field, value in (("totalRows", True), ("totalRows", 2**63),
                             ("totalRows", -1), ("unplacedNum", 1.0),
                             ("unplacedNum", 2**63)):
            invalid = dict(good, **{field: value})
            with self.subTest(field=field, value=type(value).__name__), self.assertRaises(
                    ControllerUnplacedSitePositionError):
                project_unplaced_site_positions(invalid)
        for change in (
            {"currentPage": 2}, {"currentSize": 101}, {"currentSize": 0},
            {"totalRows": 0}, {"data": None},
        ):
            with self.subTest(change=change), self.assertRaises(ControllerUnplacedSitePositionError):
                project_unplaced_site_positions({**good, **change})
        too_many = [{"id": "x"} for _ in range(PAGE_SIZE + 1)]
        with self.assertRaises(ControllerUnplacedSitePositionError):
            project_unplaced_site_positions(page(too_many, total=len(too_many), current_size=PAGE_SIZE))


if __name__ == "__main__":
    unittest.main()
