from __future__ import annotations

import unittest

from app.global_device_summary import GlobalDeviceSummaryError, project_global_device_summary


class GlobalDeviceSummaryTests(unittest.TestCase):
    def test_known_and_unknown_rows_are_projected_without_identifiers(self) -> None:
        for kind, row in (
            ("known", {"mac": "aa:bb:cc:dd:ee:ff", "name": "private", "ip": "10.0.0.4",
                        "sn": "serial", "type": "ap", "status": 1,
                        "deviceSeriesType": 1, "siteName": "private-site"}),
            ("unknown", {"mac": "aa:bb:cc:dd:ee:ff", "name": "private", "ip": "10.0.0.4",
                          "type": "switch", "status": 0, "deviceSeriesType": 0}),
        ):
            with self.subTest(kind=kind):
                result = project_global_device_summary(
                    {"data": [row], "totalRows": 3, "currentPage": 1, "currentSize": 1},
                    kind=kind, page_size=100)
                self.assertTrue(result["partial"])
                self.assertEqual(result["data"]["device_count"], 3)
                self.assertEqual(result["data"]["sampled_count"], 1)
                self.assertNotIn("private", repr(result))
                self.assertNotIn("10.0.0.4", repr(result))
                self.assertNotIn("aa:bb", repr(result))
        known = project_global_device_summary(
            {"data": [{"type": "ap", "status": 1, "deviceSeriesType": 1}],
             "totalRows": 1, "currentPage": 1, "currentSize": 1},
            kind="known", page_size=100)
        self.assertEqual(known["data"]["type_counts"], {"access_point": 1})
        self.assertEqual(known["data"]["status_code_counts"], {"1": 1})
        self.assertEqual(known["data"]["series_type_counts"], {"pro": 1})
        self.assertFalse(known["partial"])

    def test_unknown_values_and_malformed_pages_are_counted_or_rejected(self) -> None:
        partial = project_global_device_summary(
            {"data": [{"type": "future-device", "status": 9, "deviceSeriesType": 7,
                       "futurePrivateField": "drop"}],
             "totalRows": 1, "currentPage": 1, "currentSize": 1},
            kind="unknown", page_size=100)
        self.assertTrue(partial["partial"])
        self.assertEqual(partial["data"]["unknown_field_count"], 1)
        self.assertEqual(partial["data"]["unknown_value_count"], 3)
        self.assertNotIn("futurePrivateField", repr(partial))
        for page in (
            {"data": [], "totalRows": 0, "currentPage": 2, "currentSize": 0},
            {"data": [{}] * 101, "totalRows": 101, "currentPage": 1, "currentSize": 101},
            {"data": [], "totalRows": True, "currentPage": 1, "currentSize": 0},
        ):
            with self.subTest(page=page), self.assertRaises(GlobalDeviceSummaryError):
                project_global_device_summary(page, kind="known", page_size=100)


if __name__ == "__main__":
    unittest.main()
