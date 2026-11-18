import unittest

from app.site_beacon_control import SiteBeaconControlError, project_site_beacon_control


class SiteBeaconControlTests(unittest.TestCase):
    def test_projects_schema_bounded_wlan_settings(self):
        result = project_site_beacon_control({
            "beaconControl": {
                "beaconInterval2g": 100, "dtimPeriod2g": 2, "rtsThreshold2g": 2347,
                "dtimPeriod5g": 3, "rtsThreshold5g": 2200,
                "dtimPeriod6g": 1, "rtsThreshold6g": 2100,
                "probeResponseMaxRetransNum2g": 2,
                "probeResponseReplyThresholdEnable5g": True,
                "probeResponseReplyThreshold5g": -72,
            },
            "airtimeFairness": {"enable2g": True, "enable5g": False, "enable6g": True},
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["beacon_interval_2g"], 100)
        self.assertEqual(result["data"]["probe_response_threshold_dbm_5g"], -72)
        self.assertTrue(result["data"]["airtime_fairness_enabled_6g"])

    def test_counts_invalid_missing_and_unknown_without_echoing(self):
        result = project_site_beacon_control({
            "beaconControl": {"dtimPeriod2g": 999, "rtsThreshold2g": True, "private": "secret"},
            "airtimeFairness": {"enable2g": "yes"},
        })
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertGreater(result["missing_field_count"], 0)
        self.assertNotIn("secret", repr(result))
        with self.assertRaises(SiteBeaconControlError):
            project_site_beacon_control({str(i): i for i in range(5)})


if __name__ == "__main__":
    unittest.main()
