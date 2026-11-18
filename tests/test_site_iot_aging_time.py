import unittest

from app.site_iot_aging_time import (
    SiteIotAgingTimeError, project_site_iot_aging_time,
)


class SiteIotAgingTimeTests(unittest.TestCase):
    def test_projects_documented_value_and_unit(self):
        for fmt, value, unit in ((0, 30, "seconds"), (1, 1440, "minutes"),
                                 (2, 24, "hours")):
            with self.subTest(fmt=fmt):
                result = project_site_iot_aging_time({
                    "agingTime_iotAgingTime": value, "format_iotAgingTime": fmt,
                })
                self.assertEqual(result["data"], {"aging_value": value, "unit": unit})
                self.assertFalse(result["partial"])

    def test_rejects_invalid_ranges_types_and_unknown_fields_safely(self):
        result = project_site_iot_aging_time({
            "agingTime_iotAgingTime": 29, "format_iotAgingTime": 0,
            "secret": "private",
        })
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["data"], {})
        self.assertNotIn("private", repr(result))
        self.assertEqual(project_site_iot_aging_time({
            "agingTime_iotAgingTime": True, "format_iotAgingTime": 9,
        })["invalid_field_count"], 2)
        with self.assertRaises(SiteIotAgingTimeError):
            project_site_iot_aging_time({str(i): i for i in range(9)})


if __name__ == "__main__":
    unittest.main()
