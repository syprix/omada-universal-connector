from __future__ import annotations

import unittest

from app.site_switch_support import (
    FIELDS, SiteSwitchSupportError, project_site_switch_support,
)


class SiteSwitchSupportTests(unittest.TestCase):
    def test_each_exported_flag_maps_independently_as_a_strict_boolean(self) -> None:
        for source, target in FIELDS.items():
            with self.subTest(source=source):
                result = project_site_switch_support({source: False})
                self.assertEqual(result["data"]["switch_support"], {target: False})
                self.assertEqual(result["data"]["present_count"], 1)
                self.assertEqual(result["data"]["missing_count"], 1)
                self.assertTrue(result["partial"])

    def test_projects_complete_support_flags(self) -> None:
        result = project_site_switch_support({"supportES": True, "supportL2": False})
        self.assertEqual(result["data"]["switch_support"],
                         {"support_es": True, "support_l2": False})
        self.assertEqual(result["data"]["missing_count"], 0)
        self.assertFalse(result["partial"])

    def test_invalid_and_unknown_fields_are_counted_without_echoing_them(self) -> None:
        result = project_site_switch_support({
            "supportES": 1, "supportL2": True, "privateLabel": "must-not-appear"})
        self.assertEqual(result["data"]["switch_support"], {"support_l2": True})
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("privateLabel", repr(result))
        self.assertNotIn("must-not-appear", repr(result))
        self.assertTrue(result["partial"])

    def test_rejects_invalid_or_oversized_payloads(self) -> None:
        for value in (None, [], {str(index): True for index in range(17)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(SiteSwitchSupportError):
                project_site_switch_support(value)


if __name__ == "__main__":
    unittest.main()
