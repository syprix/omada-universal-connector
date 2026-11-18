import unittest

from app.site_iot_transmit_power import (
    SiteIotTransmitPowerError, project_site_iot_transmit_power,
)


class SiteIotTransmitPowerTests(unittest.TestCase):
    def test_aggregates_page_without_exposing_device_identity(self):
        result = project_site_iot_transmit_power({
            "totalRows": 105, "currentPage": 1, "currentSize": 100,
            "data": [
                {"mac": "aa:bb:cc:dd:ee:ff", "name": "Private AP", "ip": "192.0.2.4",
                 "statusCategory": 1, "transmitPower": 14, "override": True},
                {"mac": "11:22:33:44:55:66", "statusCategory": 3,
                 "transmitPower": 14, "override": False},
                {"statusCategory": 4, "transmitPower": -6},
            ],
        })
        self.assertEqual(result["data"]["observed_row_count"], 3)
        self.assertEqual(result["data"]["total_row_count"], 105)
        self.assertTrue(result["data"]["more_rows_available"])
        self.assertEqual(result["data"]["transmit_power_device_counts_dbm"], {"-6": 1, "14": 2})
        self.assertEqual(result["data"]["device_status_category_counts"]["connected"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("Private AP", repr(result))
        self.assertNotIn("192.0.2.4", repr(result))
        self.assertNotIn("aa:bb:cc:dd:ee:ff", repr(result))

    def test_rejects_oversized_pages_and_counts_invalid_or_unknown_fields(self):
        result = project_site_iot_transmit_power({
            "totalRows": -1,
            "data": [{"statusCategory": 9, "transmitPower": True,
                      "override": "yes", "secret_field": "hidden"}],
        })
        self.assertEqual(result["invalid_field_count"], 4)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SiteIotTransmitPowerError):
            project_site_iot_transmit_power({"data": [{}] * 101})


if __name__ == "__main__":
    unittest.main()
