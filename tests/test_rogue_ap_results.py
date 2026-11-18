import unittest

from app.rogue_ap_results import RogueApResultsError, summarize_rogue_ap_results


class RogueApResultsTests(unittest.TestCase):
    def test_aggregates_stored_scan_fields_and_omits_identities(self) -> None:
        result = summarize_rogue_ap_results([
            {"id": "record-secret", "ssid": "private-ssid", "bssid": "aa:bb:cc:dd:ee:ff",
             "radioId": 0, "security": 3, "beacon": 100, "channel": 6,
             "nearestApMac": "11:22:33:44:55:66", "nearestAp": "private-ap",
             "mode": 2, "signal": -55, "lastSeen": 1800000000000},
            {"radioId": 0, "security": 3, "channel": 6, "mode": 2, "signal": -75},
            {"radioId": 3, "security": 15, "channel": 5, "mode": 6, "signal": -65},
        ])
        self.assertEqual(result["resource"], "site_rogue_ap_results")
        self.assertEqual(result["summary"]["by_radio_id"], {0: 2, 3: 1})
        self.assertEqual(result["summary"]["by_channel"], {5: 1, 6: 2})
        self.assertEqual(result["summary"]["by_security_code"], {3: 2, 15: 1})
        self.assertEqual(result["summary"]["signal_dbm"], {
            "minimum": -75, "maximum": -55, "average": -65, "sample_count": 3,
        })
        for private in ("record-secret", "private-ssid", "aa:bb:cc:dd:ee:ff",
                        "private-ap", "lastSeen"):
            self.assertNotIn(private, repr(result))
        self.assertEqual(result["data_age"], "unknown_stored_scan")
        self.assertFalse(result["partial"])

    def test_unknown_codes_and_invalid_values_are_marked_partial(self) -> None:
        result = summarize_rogue_ap_results([{
            "radioId": 8, "security": 99, "mode": 99,
            "channel": True, "signal": -50, "vendorValue": "x",
        }])
        self.assertTrue(result["partial"])
        self.assertEqual(result["summary"]["unknown_radio_count"], 1)
        self.assertEqual(result["summary"]["unknown_security_count"], 1)
        self.assertEqual(result["summary"]["unknown_mode_count"], 1)
        self.assertEqual(result["summary"]["invalid_field_count"], 1)
        self.assertEqual(result["summary"]["unknown_field_count"], 1)

    def test_bounds_input_rows(self) -> None:
        with self.assertRaises(RogueApResultsError):
            summarize_rogue_ap_results([{}] * 10_001)


if __name__ == "__main__":
    unittest.main()
