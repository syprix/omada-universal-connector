import unittest

from app.site_mdns_profile_summary import MAX_PROFILES, summarize_mdns_profiles


class MdnsProfileSummaryTests(unittest.TestCase):
    def test_counts_defaults_and_service_entries_without_profile_values(self):
        result = summarize_mdns_profiles({"data": [
            {"id": "private-id", "name": "Private Name", "defaultProfile": True,
             "serviceIds": ["_printer._tcp.local"]},
            {"id": "private-id-2", "name": "Other", "defaultProfile": False,
             "serviceIds": ["_x._tcp.local", "_y._udp.local"]},
        ]})
        self.assertEqual(result["profile_count"], 2)
        self.assertEqual(result["default_profile_flags"],
                         {"true": 1, "false": 1, "unreported": 0, "invalid": 0})
        self.assertEqual(result["service_entries_per_profile"], {
            "zero": 0, "one": 1, "two": 1, "three": 0,
            "unreported": 0, "invalid": 0,
        })
        self.assertNotIn("private-id", repr(result))
        self.assertNotIn("Private Name", repr(result))
        self.assertNotIn("_printer._tcp.local", repr(result))

    def test_empty_missing_and_invalid_data_are_distinct(self):
        self.assertEqual(summarize_mdns_profiles({"data": []}), {
            "result_state": "empty", "profile_count": 0,
            "default_profile_flags": {"true": 0, "false": 0, "unreported": 0,
                                      "invalid": 0},
            "service_entries_per_profile": {"zero": 0, "one": 0, "two": 0,
                                             "three": 0, "unreported": 0,
                                             "invalid": 0},
            "invalid_profile_rows": 0, "unknown_profile_field_count": 0,
            "truncated": False, "partial": False,
        })
        self.assertEqual(summarize_mdns_profiles({})["result_state"], "missing")
        self.assertEqual(summarize_mdns_profiles({"data": "not rows"})["result_state"],
                         "invalid")

    def test_missing_fields_invalid_flags_and_unknown_fields_mark_partial(self):
        result = summarize_mdns_profiles({"data": [
            {"serviceIds": [], "extra": "private-value"},
            {"defaultProfile": 1, "serviceIds": ["ok", 5]},
            None,
        ]})
        self.assertTrue(result["partial"])
        self.assertEqual(result["default_profile_flags"],
                         {"true": 0, "false": 0, "unreported": 1, "invalid": 2})
        self.assertEqual(result["service_entries_per_profile"]["unreported"], 0)
        self.assertEqual(result["service_entries_per_profile"]["invalid"], 2)
        self.assertEqual(result["unknown_profile_field_count"], 1)
        self.assertNotIn("private-value", repr(result))

    def test_service_entries_follow_documented_three_item_limit(self):
        result = summarize_mdns_profiles({"data": [
            {"serviceIds": ["a", "b", "c"]},
            {"serviceIds": ["a", "b", "c", "d"]},
        ]})
        self.assertEqual(result["service_entries_per_profile"]["three"], 1)
        self.assertEqual(result["service_entries_per_profile"]["invalid"], 1)
        self.assertTrue(result["partial"])

    def test_profile_rows_are_bounded_and_report_truncation(self):
        result = summarize_mdns_profiles({"data": [{"serviceIds": []}] * (MAX_PROFILES + 1)})
        self.assertEqual(result["result_state"], "truncated")
        self.assertEqual(result["profile_count"], MAX_PROFILES)
        self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()
