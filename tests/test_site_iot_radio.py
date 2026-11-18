import unittest

from app.site_iot_radio import SiteIotRadioError, project_site_iot_radio


class SiteIotRadioTests(unittest.TestCase):
    def test_projects_settings_and_redacts_six_digit_passcode(self):
        result = project_site_iot_radio({
            "enable": True, "consoleMode": 0, "passcode": "987654",
            "transmitPower": -20, "agingTime": 30, "format": 0, "resource": 3,
        })
        self.assertEqual(result["data"], {
            "bluetooth_enabled": True, "console_mode": "auto",
            "passcode_configured": True, "transmit_power_dbm": -20,
            "aging_value": 30, "aging_unit": "seconds", "resource_present": True,
        })
        self.assertNotIn("987654", repr(result))
        self.assertFalse(result["partial"])

    def test_invalid_and_unknown_fields_are_counted_without_echoing_values(self):
        result = project_site_iot_radio({
            "enable": "yes", "consoleMode": 9, "passcode": "secret",
            "transmitPower": 99, "agingTime": 25, "format": 2, "newSecret": "private",
        })
        self.assertEqual(result["invalid_field_count"], 5)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("private", repr(result))
        with self.assertRaises(SiteIotRadioError):
            project_site_iot_radio({str(i): i for i in range(17)})

    def test_incomplete_aging_pair_is_partial(self):
        result = project_site_iot_radio({"enable": False, "format": 0})
        self.assertEqual(result["missing_field_count"], 1)
        self.assertNotIn("aging_value", result["data"])
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
