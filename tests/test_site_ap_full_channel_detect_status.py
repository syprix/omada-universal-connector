import unittest

from app.site_ap_full_channel_detect_status import project_ap_full_channel_detect_status


class ApFullChannelDetectStatusTests(unittest.TestCase):
    def test_maps_documented_codes_without_timestamp_or_ap_identity(self):
        result = project_ap_full_channel_detect_status({
            "status": 3, "wifiInterfStatus": 0, "interfStatus": 1,
            "channelLoadStatus": 3, "lastSeen": 1700000000000,
            "fromGlobal": True, "mac": "private"})
        self.assertEqual(result["data"]["statuses"], {
            "full_channel_detection": "scanning",
            "wifi_interference": "unscanned_with_result",
            "interference": "unscanned_without_result",
            "channel_load": "scanning"})
        self.assertTrue(result["data"]["last_seen_present"])
        self.assertTrue(result["data"]["from_global"])
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("1700000000000", repr(result))
        self.assertNotIn("private", repr(result))

    def test_invalid_and_missing_statuses_are_not_given_default_meaning(self):
        result = project_ap_full_channel_detect_status({"status": 2,
                                                        "wifiInterfStatus": True})
        self.assertEqual(result["data"]["statuses"], {})
        self.assertEqual(result["data"]["invalid_field_count"], 2)
        self.assertEqual(result["data"]["missing_field_count"], 2)
        self.assertTrue(result["partial"])

    def test_rejects_wrong_result_shape(self):
        with self.assertRaises(ValueError):
            project_ap_full_channel_detect_status([])


if __name__ == "__main__":
    unittest.main()
