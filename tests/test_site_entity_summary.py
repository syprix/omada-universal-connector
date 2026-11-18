from __future__ import annotations

import unittest

from app.site_entity_summary import SiteEntitySummaryError, summarize_site_entity


class SiteEntitySummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entity = {
            "siteId": "private-site-id", "name": "Secret Site", "type": 0,
            "tagIds": ["private-tag"], "region": "Example Region",
            "timeZone": "Secret/Zone", "ntpEnable": True,
            "ntpServers": ["private.ntp", "192.0.2.10"],
            "dst": {"enable": False, "mode": 0, "status": False,
                    "timeZone": "Secret/Zone", "startTime": 1},
            "scenario": "private-scenario", "longitude": 12.5,
            "latitude": -7.25, "address": "Private address",
            "supportES": True, "supportL2": False,
        }

    def test_read_site_entity_summary_returns_only_bounded_metadata(self) -> None:
        result = summarize_site_entity(self.entity)
        self.assertEqual(result, {
            "data": {"site_tier": "basic", "ntp_enabled": True,
                     "ntp_server_count": 2, "timezone_configured": True,
                     "dst_enabled": False, "location_configured": True,
                     "supports_agile_switches": True,
                     "supports_non_agile_switches": False},
            "missing_field_count": 0, "invalid_field_count": 0,
            "unknown_field_count": 0, "partial": False,
        })
        serialized = repr(result)
        for private in ("private-site-id", "Secret Site", "private-tag",
                        "Example Region", "Secret/Zone", "private.ntp",
                        "192.0.2.10", "private-scenario", "Private address", "12.5", "-7.25"):
            self.assertNotIn(private, serialized)

    def test_missing_invalid_and_unknown_fields_are_partial(self) -> None:
        value = {"type": True, "ntpEnable": 1, "ntpServers": ["x"] * 6,
                 "dst": {"enable": "yes", "unexpected": True},
                 "supportES": False, "supportL2": True,
                 "timeZone": "", "longitude": 181, "latitude": -90,
                 "newSourceField": "discard"}
        result = summarize_site_entity(value)
        self.assertTrue(result["partial"])
        self.assertIsNone(result["data"]["site_tier"])
        self.assertIsNone(result["data"]["ntp_enabled"])
        self.assertIsNone(result["data"]["ntp_server_count"])
        self.assertIsNone(result["data"]["dst_enabled"])
        self.assertIsNone(result["data"]["location_configured"])
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertGreater(result["invalid_field_count"], 0)

    def test_non_object_and_non_finite_coordinates_are_rejected_or_partial(self) -> None:
        with self.assertRaises(SiteEntitySummaryError):
            summarize_site_entity([self.entity])
        value = dict(self.entity, longitude=float("nan"), latitude=0)
        result = summarize_site_entity(value)
        self.assertTrue(result["partial"])
        self.assertIsNone(result["data"]["location_configured"])


if __name__ == "__main__":
    unittest.main()
