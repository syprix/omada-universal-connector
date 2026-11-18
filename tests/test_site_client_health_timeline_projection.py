from __future__ import annotations

import unittest

from app.site_client_health_timeline import (
    SiteClientHealthTimelineError,
    project_site_client_health_timeline,
)


START = 1_800_000_000_000
END = START + 86_400_000


class SiteClientHealthTimelineProjectionTests(unittest.TestCase):
    def test_projects_documented_distribution_counts_and_millisecond_time(self) -> None:
        result = project_site_client_health_timeline({"scores": [{
            "time": START,
            "scoreDetail": {"goodCount": 2, "averageCount": 3,
                            "poorCount": 4, "noDataCount": 5},
        }]}, START, END)
        self.assertFalse(result["partial"])
        self.assertEqual(result["resource"], "site_client_health_timeline")
        self.assertEqual(result["data"], {"scores": [{
            "time_ms": START,
            "score_detail": {"good_count": 2, "average_count": 3,
                             "poor_count": 4, "no_data_count": 5},
        }]})
        self.assertEqual(result["discarded_outside_window"], 0)

    def test_empty_timeline_is_valid_and_missing_timeline_is_partial(self) -> None:
        empty = project_site_client_health_timeline({"scores": []}, START, END)
        self.assertFalse(empty["partial"])
        self.assertEqual(empty["data"], {"scores": []})
        missing = project_site_client_health_timeline({}, START, END)
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["missing_fields"], ["scores"])

    def test_unknown_and_identity_fields_are_not_returned(self) -> None:
        result = project_site_client_health_timeline({
            "scores": [{"time": START, "scoreDetail": {
                "goodCount": 1, "averageCount": 2, "poorCount": 3,
                "noDataCount": 4, "clientName": "private-client",
            }, "siteId": "private-site"}],
            "clientMac": "AA:BB:CC:DD:EE:FF",
        }, START, END)
        self.assertTrue(result["partial"])
        self.assertIn("unknown_fields", result["omitted_fields"])
        for secret in ("private-client", "private-site", "clientMac", "AA:BB:CC:DD:EE:FF"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_counts_and_out_of_window_points_mark_partial(self) -> None:
        result = project_site_client_health_timeline({"scores": [
            {"time": START, "scoreDetail": {
                "goodCount": True, "averageCount": -1,
                "poorCount": 2**31, "noDataCount": 0,
            }},
            {"time": True, "scoreDetail": {"goodCount": 1}},
            {"time": END + 1, "scoreDetail": {"goodCount": 0}},
            "invalid-row",
        ]}, START, END)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["scores"], [{
            "time_ms": START, "score_detail": {"no_data_count": 0},
        }])
        self.assertEqual(result["discarded_outside_window"], 1)
        self.assertIn("invalid_points", result["omitted_fields"])
        self.assertIn("invalid_timestamps", result["omitted_fields"])

    def test_bounds_and_malformed_windows_fail_closed(self) -> None:
        for raw, start, end in (
            (None, START, END),
            ({"scores": [None] * 257}, START, END),
            ({"scores": []}, True, END),
            ({"scores": []}, START, START + 1),
        ):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(SiteClientHealthTimelineError):
                project_site_client_health_timeline(raw, start, end)


if __name__ == "__main__":
    unittest.main()
