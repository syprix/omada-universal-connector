from __future__ import annotations

import unittest

from app.channel_dashboard import (
    ChannelDashboardError,
    project_site_dashboard_channels,
)


def row(channel: int = 36, utilization: object = 12.5) -> dict[str, object]:
    return {
        "channel": channel,
        "apNum": 2,
        "clientNum": 7,
        "channelUtilization": utilization,
    }


class SiteDashboardChannelsTests(unittest.TestCase):
    def test_projects_allowlisted_channel_statistics(self) -> None:
        result = project_site_dashboard_channels({
            "2g channel stat": [row(6, None)],
            "5g channel stat": [row()],
            "6g channel stat": [],
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {"bands": {
            "2g": [{"channel": 6, "ap_count": 2, "client_count": 7,
                    "utilization_percent": None}],
            "5g": [{"channel": 36, "ap_count": 2, "client_count": 7,
                    "utilization_percent": 12.5}],
            "6g": [],
        }})
        self.assertEqual(result["omitted_field_count"], 0)

    def test_missing_band_is_partial_and_not_fabricated_as_empty(self) -> None:
        result = project_site_dashboard_channels({"2g channel stat": []})
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"], {"bands": {"2g": []}})
        self.assertEqual(result["missing_fields"], [
            "5g channel stat", "6g channel stat",
        ])

    def test_missing_invalid_and_unknown_row_fields_are_partial_and_redacted(self) -> None:
        result = project_site_dashboard_channels({
            "2g channel stat": [{
                "channel": 1, "apNum": True, "clientNum": 4,
                "channelUtilization": 20, "apName": "private-ap",
                "mac": "aa:bb:cc:dd:ee:ff",
            }],
            "5g channel stat": [{"channel": 36}],
            "6g channel stat": [],
            "siteName": "private-site",
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["bands"]["2g"], [{
            "channel": 1, "client_count": 4, "utilization_percent": 20,
        }])
        self.assertEqual(result["data"]["bands"]["5g"], [{"channel": 36}])
        rendered = repr(result)
        for secret in ("private-ap", "aa:bb:cc:dd:ee:ff", "private-site"):
            self.assertNotIn(secret, rendered)
        self.assertIn("unknown_fields", result["omitted_fields"])

    def test_invalid_arrays_and_invalid_numeric_values_are_omitted(self) -> None:
        for bad in (None, {}, "[]"):
            with self.subTest(value=bad):
                result = project_site_dashboard_channels({
                    "2g channel stat": bad,
                    "5g channel stat": [row(utilization=float("nan"))],
                    "6g channel stat": [row(utilization=float("inf"))],
                })
                self.assertTrue(result["partial"])
                self.assertNotIn("2g", result["data"]["bands"])
                self.assertNotIn("utilization_percent", result["data"]["bands"]["5g"][0])
                self.assertNotIn("utilization_percent", result["data"]["bands"]["6g"][0])

    def test_rejects_bool_negative_or_overflow_integer_and_bad_percent(self) -> None:
        for field, bad_value in (
            ("channel", True), ("channel", -1), ("apNum", 2_147_483_648),
            ("clientNum", "1"), ("channelUtilization", True),
            ("channelUtilization", -0.1), ("channelUtilization", 100.1),
            ("channelUtilization", 10 ** 10000),
        ):
            with self.subTest(field=field, value=bad_value):
                item = row()
                item[field] = bad_value
                result = project_site_dashboard_channels({
                    "2g channel stat": [item],
                    "5g channel stat": [],
                    "6g channel stat": [],
                })
                self.assertTrue(result["partial"])
                projected_row = result["data"]["bands"]["2g"][0]
                output_field = {
                    "apNum": "ap_count", "clientNum": "client_count",
                    "channelUtilization": "utilization_percent",
                }.get(field, field)
                self.assertNotIn(output_field, projected_row)

    def test_size_bounds_and_non_object_fail_with_fixed_error(self) -> None:
        for raw in (
            None,
            [],
            {"2g channel stat": [row()] * 257},
            {f"field-{i}": i for i in range(65)},
        ):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ChannelDashboardError):
                project_site_dashboard_channels(raw)


if __name__ == "__main__":
    unittest.main()
