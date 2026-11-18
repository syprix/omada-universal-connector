import unittest

from app.site_ap_rssi_density import SiteApRssiDensityError, project_site_ap_rssi_density


class SiteApRssiDensityTests(unittest.TestCase):
    def test_returns_bucket_counts_without_access_point_rows(self):
        payload = {"existAp": True, "existApClient": True}
        payload.update({field: [] for field in (
            "lessThan90", "from90To85", "from85To80", "from80To75", "from75To70",
            "from70To65", "from65To60", "from60To55", "from55To50", "from50To45",
            "from45To40", "from40To35", "from35To30", "moreThan30")})
        payload["lessThan90"] = [{"name": "private-ap", "mac": "private-id"}]
        result = project_site_ap_rssi_density(payload)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["ap_count_in_buckets"], 1)
        self.assertEqual(result["data"]["ap_count_by_signal_bucket"]["less_than_90"], 1)
        self.assertNotIn("private-ap", repr(result))
        self.assertNotIn("private-id", repr(result))

    def test_marks_missing_and_invalid_fields_and_enforces_row_bound(self):
        result = project_site_ap_rssi_density({"existAp": 1, "lessThan90": [{"x": 1}] * 1001})
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["missing_field_count"], 14)
        with self.assertRaises(SiteApRssiDensityError):
            project_site_ap_rssi_density({str(i): i for i in range(19)})


if __name__ == "__main__":
    unittest.main()
