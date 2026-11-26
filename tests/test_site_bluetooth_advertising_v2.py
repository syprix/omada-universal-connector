import unittest

from app.site_bluetooth_advertising_v2 import (
    SiteBluetoothAdvertisingV2Error, project_site_bluetooth_advertising_v2,
)


class SiteBluetoothAdvertisingV2Tests(unittest.TestCase):
    def test_projects_only_aggregate_counts_and_hides_beacon_fields(self):
        marker = "SENSITIVE-BEACON-MARKER"
        result = project_site_bluetooth_advertising_v2({
            "totalRows": 2, "currentPage": 1, "currentSize": 100,
            "data": [
                {"id": marker, "name": marker, "boundDeviceNum": 3,
                 "macList": [marker], "enable": True, "transmitPower": 19,
                 "measurePower": -59, "advInterval": 100, "uuid": marker,
                 "major": marker, "minor": marker,
                 "selectMacInfo": [{"mac": marker, "name": marker}], "buildIn": 1},
                {"name": marker, "boundDeviceNum": 0, "enable": False},
            ],
        })
        self.assertEqual(result["data"]["observed_row_count"], 2)
        self.assertEqual(result["data"]["total_row_count"], 2)
        self.assertEqual(result["data"]["enabled_count"], 1)
        self.assertEqual(result["data"]["disabled_count"], 1)
        self.assertEqual(result["data"]["bound_device_count_valid_rows"], 2)
        self.assertTrue(result["partial"])
        self.assertNotIn(marker, repr(result))
        self.assertNotIn("transmit_power", repr(result))

    def test_accepts_empty_grid_and_marks_missing_metadata_partial(self):
        result = project_site_bluetooth_advertising_v2({
            "totalRows": 0, "currentPage": 1, "currentSize": 100, "data": [],
        })
        self.assertEqual(result["data"]["observed_row_count"], 0)
        self.assertFalse(result["partial"])
        partial = project_site_bluetooth_advertising_v2({"data": []})
        self.assertTrue(partial["partial"])
        self.assertGreater(partial["missing_field_count"], 0)

    def test_counts_missing_invalid_and_unknown_without_values(self):
        result = project_site_bluetooth_advertising_v2({
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"name": "safe-to-redact", "enable": None,
                      "boundDeviceNum": True, "unknown_secret": "DO-NOT-RETURN"}],
        })
        self.assertEqual(result["data"]["enable_invalid_count"], 1)
        self.assertEqual(result["data"]["bound_device_count_invalid_rows"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("DO-NOT-RETURN", repr(result))
        self.assertNotIn("safe-to-redact", repr(result))

    def test_rejects_wrong_grid_shape_and_more_than_one_page(self):
        for grid in (None, [], {"data": "not-a-grid"}, {"data": [{}] * 101}):
            with self.subTest(grid_type=type(grid).__name__):
                with self.assertRaises(SiteBluetoothAdvertisingV2Error):
                    project_site_bluetooth_advertising_v2(grid)

    def test_negative_bound_device_count_is_invalid_once_and_partial(self):
        result = project_site_bluetooth_advertising_v2({
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"name": "x", "enable": True, "boundDeviceNum": -1}],
        })
        self.assertEqual(result["data"]["bound_device_count_invalid_rows"], 1)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertTrue(result["partial"])

    def test_bound_device_count_type_and_range_errors_count_once(self):
        for value in (True, 2 ** 31):
            with self.subTest(value_type=type(value).__name__):
                result = project_site_bluetooth_advertising_v2({
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "data": [{"name": "x", "enable": True, "boundDeviceNum": value}],
                })
                self.assertEqual(result["data"]["bound_device_count_invalid_rows"], 1)
                self.assertEqual(result["invalid_field_count"], 1)
                self.assertTrue(result["partial"])

    def test_rejects_inconsistent_page_provenance(self):
        row = {"name": "x", "enable": True, "boundDeviceNum": 0}
        invalid_grids = (
            {"totalRows": 1, "currentPage": 2, "currentSize": 1, "data": [row]},
            {"totalRows": 1, "currentPage": 1, "currentSize": 99, "data": [row]},
            {"totalRows": 0, "currentPage": 1, "currentSize": 1, "data": [row]},
        )
        for grid in invalid_grids:
            with self.subTest(current_page=grid["currentPage"], current_size=grid["currentSize"]):
                with self.assertRaises(SiteBluetoothAdvertisingV2Error):
                    project_site_bluetooth_advertising_v2(grid)

    def test_accepts_short_page_and_reports_large_total_as_partial(self):
        short = project_site_bluetooth_advertising_v2({
            "totalRows": 2, "currentPage": 1, "currentSize": 2,
            "data": [{"name": "a", "enable": True, "boundDeviceNum": 0},
                     {"name": "b", "enable": False, "boundDeviceNum": 1}],
        })
        self.assertEqual(short["data"]["observed_row_count"], 2)
        self.assertEqual(short["data"]["total_row_count"], 2)
        self.assertTrue(short["partial"])

        large = project_site_bluetooth_advertising_v2({
            "totalRows": 101, "currentPage": 1, "currentSize": 100,
            "data": [{"name": "x", "enable": True, "boundDeviceNum": 0} for _ in range(100)],
        })
        self.assertEqual(large["data"]["observed_row_count"], 100)
        self.assertEqual(large["data"]["total_row_count"], 101)
        self.assertTrue(large["partial"])


if __name__ == "__main__":
    unittest.main()
