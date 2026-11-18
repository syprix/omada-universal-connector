import unittest

from app.wids_summary import WidsSummaryError, summarize_wids_results


class WidsSummaryTests(unittest.TestCase):
    def test_aggregates_documented_codes_and_redacts_all_identifiers(self) -> None:
        result = summarize_wids_results([
            {"stationMac": "station-secret", "stationMacList": ["mac-secret"],
             "detectMac": "ap-secret", "channel": 6, "band": 0,
             "startTime": 1800000000000, "type": 17, "level": 0},
            {"stationMac": "another-secret", "channel": 6, "band": 0,
             "type": 17, "level": 1},
            {"band": 3, "channel": 149, "type": 99, "level": 2},
        ], total_rows=3)
        self.assertEqual(result["resource"], "site_wids_summary")
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["total_rows"], 3)
        self.assertEqual(result["summary"]["by_level_code"], {0: 1, 1: 1, 2: 1})
        self.assertEqual(result["summary"]["by_type_code"], {17: 2, 99: 1})
        self.assertEqual(result["summary"]["by_band_code"], {0: 2, 3: 1})
        self.assertEqual(result["summary"]["by_channel"], {6: 2, 149: 1})
        self.assertFalse(result["partial"])
        for private in ("station-secret", "mac-secret", "ap-secret", "1800000000000"):
            self.assertNotIn(private, repr(result))

    def test_unknown_codes_fields_and_invalid_values_are_reported_not_inferred(self) -> None:
        result = summarize_wids_results([
            {"level": 99, "band": 8, "type": 2**31, "channel": True,
             "stationMacList": ["x"], "vendorField": "private"},
            None,
        ], total_rows=2)
        self.assertTrue(result["partial"])
        self.assertEqual(result["summary"]["unknown_level_count"], 1)
        self.assertEqual(result["summary"]["unknown_band_count"], 1)
        self.assertEqual(result["summary"]["invalid_field_count"], 2)
        self.assertEqual(result["summary"]["unknown_field_count"], 1)
        self.assertEqual(result["summary"]["unknown_row_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_marks_first_page_as_partial_when_more_rows_exist(self) -> None:
        result = summarize_wids_results([{"level": 0}], total_rows=1200)
        self.assertTrue(result["partial"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["total_rows"], 1200)

    def test_rejects_unbounded_or_inconsistent_envelopes(self) -> None:
        for rows, total in (([{}] * 1001, 1001), ([{}], 0), ([], True), ({}, 0)):
            with self.subTest(total=total):
                with self.assertRaises(WidsSummaryError):
                    summarize_wids_results(rows, total)


    def test_blacklist_summary_redacts_event_identities_and_times(self) -> None:
        from app.wids_summary import summarize_wids_blacklist

        result = summarize_wids_blacklist([
            {"stationMac": "station-secret", "detectMac": "ap-secret", "timeStamp": 123},
            {"stationMac": "another-secret", "timeStamp": 456},
        ], 4)
        self.assertEqual(result["resource"], "site_wids_blacklist_summary")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["total_rows"], 4)
        self.assertTrue(result["partial"])
        rendered = repr(result)
        for secret in ("station-secret", "ap-secret", "123", "456"):
            self.assertNotIn(secret, rendered)

    def test_blacklist_unknown_and_malformed_rows_mark_partial(self) -> None:
        from app.wids_summary import summarize_wids_blacklist

        result = summarize_wids_blacklist([
            {"timeStamp": True, "extra": "discard"},
            None,
        ], 2)
        self.assertTrue(result["partial"])
        self.assertEqual(result["summary"], {
            "invalid_field_count": 1,
            "unknown_field_count": 1,
            "unknown_row_count": 1,
        })


if __name__ == "__main__":
    unittest.main()
