import unittest

from app.controller_general_settings import project_controller_general_settings


class ControllerGeneralSettingsTests(unittest.TestCase):
    def test_projects_identity_locale_and_nested_dst(self):
        result = project_controller_general_settings({
            "name": "Home Controller", "timeZone": "Europe/Berlin", "region": "DE",
            "dst": {"enable": False},
        })
        self.assertEqual(result["data"]["settings"], {
            "name": "Home Controller", "time_zone": "Europe/Berlin", "region": "DE",
        })
        self.assertFalse(result["data"]["dst"]["settings"]["enabled"])
        self.assertFalse(result["partial"])

    def test_invalid_values_and_unknown_fields_are_bounded(self):
        result = project_controller_general_settings({
            "name": " bad\nname", "timeZone": 1, "region": "DE",
            "dst": {"enable": False}, "extra": "secret",
        })
        self.assertEqual(result["data"]["invalid_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("secret", str(result))
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
