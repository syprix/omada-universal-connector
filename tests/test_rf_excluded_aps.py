from __future__ import annotations

import unittest

from app.rf_excluded_aps import RfExcludedApsError, project_rf_excluded_aps


class RfExcludedApsTests(unittest.TestCase):
    def test_returns_site_opaque_refs_and_redacts_ap_identity(self) -> None:
        ref = "a" * 24
        result = project_rf_excluded_aps([{
            "mac": "AA:BB:CC:DD:EE:FF", "name": "private-ap", "ip": "192.0.2.5",
            "model": "EAP", "unsupportType": 1, "statusCategory": 1,
            "addedInAdvanced": True,
        }], {"aabbccddeeff": [ref]})
        self.assertEqual(result["items"], [{
            "ap_ref": ref, "unsupported_reason": 1, "status_category": 1,
            "added_in_advanced": True,
        }])
        self.assertFalse(result["partial"])
        for private in ("AA:BB:CC:DD:EE:FF", "private-ap", "192.0.2.5"):
            self.assertNotIn(private, repr(result))

    def test_unknown_ambiguous_and_invalid_rows_are_omitted(self) -> None:
        result = project_rf_excluded_aps([
            {"mac": "00:00:00:00:00:01"},
            {"mac": "AA:BB:CC:DD:EE:FF"},
            {"mac": "invalid"},
        ], {"aabbccddeeff": ["a" * 24, "b" * 24]})
        self.assertEqual(result["items"], [])
        self.assertEqual(result["omitted_field_count"], 3)
        self.assertTrue(result["partial"])

    def test_row_and_collection_limits_fail_closed(self) -> None:
        with self.assertRaises(RfExcludedApsError):
            project_rf_excluded_aps([{}] * 257, {})
        with self.assertRaises(RfExcludedApsError):
            project_rf_excluded_aps([{f"extra{i}": i for i in range(25)}], {})


if __name__ == "__main__":
    unittest.main()
