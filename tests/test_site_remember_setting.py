import unittest

from app.site_remember_setting import (
    SiteRememberSettingError, project_site_remember_setting,
)


class SiteRememberSettingTests(unittest.TestCase):
    def test_projects_the_documented_boolean(self):
        result = project_site_remember_setting({"remember": False})
        self.assertEqual(result["data"], {"remember_enabled": False})
        self.assertFalse(result["partial"])

    def test_counts_invalid_and_unknown_fields_without_echoing_values(self):
        result = project_site_remember_setting({"remember": "secret", "extra": "private"})
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("private", repr(result))
        with self.assertRaises(SiteRememberSettingError):
            project_site_remember_setting({str(i): i for i in range(5)})


if __name__ == "__main__":
    unittest.main()
