from __future__ import annotations

import unittest

from app.site_capabilities import FIELDS, SiteCapabilitiesError, project_site_capabilities


class SiteCapabilitiesTests(unittest.TestCase):
    def test_projects_only_documented_boolean_capabilities(self) -> None:
        raw = {key: (index % 2 == 0) for index, key in enumerate(FIELDS)}
        raw["privateDescription"] = "must-not-appear"
        result = project_site_capabilities(raw)
        self.assertEqual(result["data"]["present_count"], len(FIELDS))
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("privateDescription", repr(result))
        self.assertEqual(set(result["data"]["capabilities"]), set(FIELDS.values()))

    def test_each_documented_flag_maps_independently_to_its_public_name(self) -> None:
        for source, target in FIELDS.items():
            with self.subTest(source=source):
                result = project_site_capabilities({source: False})
                self.assertEqual(result["data"]["capabilities"], {target: False})
                self.assertEqual(result["data"]["present_count"], 1)
                self.assertEqual(result["data"]["missing_count"], len(FIELDS) - 1)
                self.assertTrue(result["partial"])

    def test_marks_missing_and_invalid_values_partial(self) -> None:
        result = project_site_capabilities({"firewall": True, "qos": 1})
        self.assertEqual(result["data"]["missing_count"], len(FIELDS) - 2)
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["capabilities"], {"firewall": True})
        self.assertTrue(result["partial"])

    def test_rejects_invalid_or_oversized_payloads(self) -> None:
        for value in (None, [], {str(index): True for index in range(129)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(SiteCapabilitiesError):
                project_site_capabilities(value)


if __name__ == "__main__":
    unittest.main()
