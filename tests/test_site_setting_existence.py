from __future__ import annotations

import unittest

from app.site_setting_existence import FIELDS, SiteSettingExistenceError, project_site_setting_existence


class SiteSettingExistenceTests(unittest.TestCase):
    def test_projects_only_documented_boolean_flags(self) -> None:
        raw = {key: (index % 2 == 0) for index, key in enumerate(FIELDS)}
        raw["privateDescription"] = "must-not-appear"
        result = project_site_setting_existence(raw)
        self.assertEqual(result["data"]["present_count"], len(FIELDS))
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("privateDescription", repr(result))
        self.assertEqual(set(result["data"]["settings"]), set(FIELDS.values()))

    def test_each_documented_flag_maps_independently_to_its_public_name(self) -> None:
        for source, target in FIELDS.items():
            with self.subTest(source=source):
                result = project_site_setting_existence({source: False})
                self.assertEqual(result["data"]["settings"], {target: False})
                self.assertEqual(result["data"]["present_count"], 1)
                self.assertEqual(result["data"]["missing_count"], len(FIELDS) - 1)
                self.assertTrue(result["partial"])

    def test_marks_missing_and_invalid_fields_partial(self) -> None:
        result = project_site_setting_existence({"dnsProxy": True, "qos": 1})
        self.assertEqual(result["data"]["missing_count"], len(FIELDS) - 2)
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["settings"], {"dns_proxy": True})
        self.assertTrue(result["partial"])

    def test_rejects_invalid_or_oversized_payloads(self) -> None:
        for value in (None, [], {str(index): True for index in range(65)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(SiteSettingExistenceError):
                project_site_setting_existence(value)


if __name__ == "__main__":
    unittest.main()
