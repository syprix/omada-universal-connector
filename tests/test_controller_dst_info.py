import unittest

from app.controller_dst_info import project_controller_dst


class ControllerDstInfoTests(unittest.TestCase):
    def test_projects_codes_rules_timestamps_and_time_zone(self):
        result = project_controller_dst({
            "enable": True, "status": True, "mode": 2, "offset": 3_600_000,
            "timeZone": "Europe/Berlin", "start": {
                "month": 3, "serial": 5, "day": 7, "hour": 2, "minute": 0,
            }, "end": {"month": 10, "serial": 5, "day": 7, "hour": 3, "minute": 0},
            "startTime": 1_800_000_000_000, "endTime": 1_810_000_000_000,
            "nextStart": 1_900_000_000_000, "nextEnd": 1_920_000_000_000,
            "lastStart": 1_700_000_000_000, "lastEnd": 1_710_000_000_000,
        })
        self.assertEqual(result["data"]["settings"], {
            "enabled": True, "available": True, "mode_code": 2,
            "offset_ms": 3_600_000, "time_zone": "Europe/Berlin",
        })
        self.assertEqual(result["data"]["time_rules"]["start_rule"]["serial"], 5)
        self.assertEqual(result["data"]["timestamps_ms"]["nextStart"], 1_900_000_000_000)
        self.assertFalse(result["partial"])

    def test_invalid_values_unknowns_and_disabled_sparse_response(self):
        result = project_controller_dst({"enable": True, "mode": 3, "offset": 1,
                                         "start": {"month": 13}, "unknown": "private"})
        self.assertEqual(result["data"]["invalid_count"], 7)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("private", str(result))
        self.assertTrue(result["partial"])
        disabled = project_controller_dst({"enable": False})
        self.assertFalse(disabled["partial"])
        self.assertTrue(disabled["data"]["settings"]["enabled"] is False)


if __name__ == "__main__":
    unittest.main()
