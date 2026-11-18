from __future__ import annotations

import unittest

from app.site_batch_interference_ap_summary import (
    SiteBatchInterferenceApSummaryError,
    summarize_site_batch_interference_ap_list,
)


class SiteBatchInterferenceApSummaryTests(unittest.TestCase):
    def test_aggregates_capabilities_without_device_identifiers(self):
        result = summarize_site_batch_interference_ap_list({
            "scanApNum": 2,
            "deviceInfoList": [
                {"mac": "00:11:22:33:44:55", "name": "Private AP",
                 "hasResult": True, "support2g": True, "support5g": False},
                {"mac": "00:11:22:33:44:66", "name": "Other AP",
                 "hasResult": False, "support2g": True, "support5g": True},
            ],
        })
        self.assertEqual(result["data"]["reported_scan_ap_count"], 2)
        self.assertEqual(result["data"]["valid_device_count"], 2)
        self.assertEqual(result["data"]["support_counts"]["support2g"]["true"], 2)
        self.assertEqual(result["data"]["support_counts"]["support5g"]["false"], 1)
        self.assertFalse(result["partial"])
        for secret in ("00:11:22:33:44:55", "Private AP", "Other AP"):
            self.assertNotIn(secret, repr(result))

    def test_emits_only_site_scoped_opaque_references_for_valid_macs(self):
        refs = {"00:11:22:33:44:55": "a" * 24,
                "00:11:22:33:44:66": "b" * 24}
        result = summarize_site_batch_interference_ap_list({
            "scanApNum": 2,
            "deviceInfoList": [
                {"mac": "00:11:22:33:44:55", "name": "Private AP"},
                {"mac": "00:11:22:33:44:66", "name": "Other AP"},
                {"mac": "invalid"},
            ],
        }, device_ref_for=refs.__getitem__)
        self.assertEqual(result["data"]["device_refs"], ["a" * 24, "b" * 24])
        self.assertNotIn("00:11:22:33:44:55", repr(result))
        self.assertNotIn("Private AP", repr(result))

    def test_invalid_unknown_missing_and_truncated_values_are_partial(self):
        bad = summarize_site_batch_interference_ap_list({
            "scanApNum": -1, "deviceInfoList": [{"support2g": "yes", "future": 1}]})
        self.assertTrue(bad["partial"])
        self.assertEqual(bad["invalid_field_count"], 2)
        self.assertEqual(bad["unknown_field_count"], 1)
        missing = summarize_site_batch_interference_ap_list({})
        self.assertEqual(missing["missing_field_count"], 2)
        self.assertTrue(missing["partial"])
        overflow = summarize_site_batch_interference_ap_list({
            "scanApNum": 501, "deviceInfoList": [{} for _ in range(501)]})
        self.assertTrue(overflow["data"]["truncated"])
        self.assertTrue(overflow["partial"])

    def test_rejects_invalid_response_envelopes(self):
        for value in (None, [], {"deviceInfoList": {}}):
            with self.subTest(value=value), self.assertRaises(
                    SiteBatchInterferenceApSummaryError):
                summarize_site_batch_interference_ap_list(value)


if __name__ == "__main__":
    unittest.main()
