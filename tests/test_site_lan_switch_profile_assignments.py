import unittest
from app.site_lan_switch_profile_assignments import (
    LanSwitchProfileError, project_lan_switch_profile_page,
)

class LanSwitchProfileAssignmentsTests(unittest.TestCase):
    def test_counts_grid_rows_and_profile_entries_without_values(self):
        result = project_lan_switch_profile_page({
            "totalRows": 2, "currentPage": 1, "currentSize": 2,
            "data": [{"name": "hidden", "mac": "aa:bb", "profiles": {"port1": "hidden-profile", "port2": "other"}},
                     {"name": "also-hidden", "mac": "cc:dd", "profiles": {}}]}, 1, 10)
        self.assertEqual((result["total_rows"], result["rows"], result["profile_assignments"]), (2, 2, 2))
        self.assertEqual(result["rows_with_profile_data"], 2)
        self.assertNotIn("hidden", str(result))

    def test_missing_profile_map_is_unknown_not_zero_and_wrapper_rejected(self):
        result = project_lan_switch_profile_page({"totalRows": 1, "currentPage": 1,
            "currentSize": 1, "data": [{"name": "n", "mac": "m"}]}, 1, 10)
        self.assertEqual(result["rows_without_profile_data"], 1)
        with self.assertRaises(LanSwitchProfileError):
            project_lan_switch_profile_page({"errorCode": 0, "result": {"totalRows": 0,
                "currentPage": 1, "currentSize": 0, "data": []}}, 1, 10)

    def test_rejects_inconsistent_page_and_er_placeholder_example(self):
        with self.assertRaises(LanSwitchProfileError):
            project_lan_switch_profile_page({"totalRows": 0, "currentPage": 0,
                "currentSize": 0, "data": [{"name": "", "mac": "", "profiles": {}}]}, 1, 10)

if __name__ == "__main__": unittest.main()
