from __future__ import annotations

import unittest

from app.roaming_settings import RoamingSettingsError, project_roaming_settings


class RoamingSettingsProjectionTests(unittest.TestCase):
    def test_projects_all_known_boolean_values_including_deprecated_fields(self) -> None:
        settings = {
            "fastRoamingEnable": True,
            "aiRoamingEnable": False,
            "dualBand11kReportEnable": True,
            "forceDisassociationEnable": False,
            "nonStickRoamingEnable": True,
        }
        result = project_roaming_settings({"roaming": settings})
        self.assertEqual(result["data"], settings)
        self.assertFalse(result["partial"])
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(result["omitted_fields"], [])
        # The projection reports observed values; it does not infer support.
        self.assertNotIn("support_state", result)

    def test_missing_fields_are_reported_and_only_present_values_are_returned(self) -> None:
        result = project_roaming_settings({"roaming": {
            "fastRoamingEnable": True,
            "aiRoamingEnable": False,
        }})
        self.assertEqual(result["data"], {
            "fastRoamingEnable": True, "aiRoamingEnable": False,
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_fields"], [
            "dualBand11kReportEnable", "forceDisassociationEnable", "nonStickRoamingEnable",
        ])

    def test_invalid_and_unknown_fields_are_marked_without_echoing_private_keys(self) -> None:
        result = project_roaming_settings({
            "roaming": {
                "fastRoamingEnable": 1,
                "aiRoamingEnable": True,
                "privateProfileId": "secret-id",
            },
            "privateSiteName": "secret-site",
        })
        self.assertEqual(result["data"], {"aiRoamingEnable": True})
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_field_count"], 6)
        self.assertEqual(result["omitted_fields"], [
            "fastRoamingEnable", "unknown_fields",
        ])
        rendered = repr(result)
        self.assertNotIn("privateProfileId", rendered)
        self.assertNotIn("privateSiteName", rendered)
        self.assertNotIn("secret-id", rendered)
        self.assertNotIn("secret-site", rendered)

    def test_missing_or_malformed_roaming_object_is_partial_without_raw_echo(self) -> None:
        missing = project_roaming_settings({})
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["missing_fields"], ["roaming"])
        malformed = project_roaming_settings({"roaming": "private-controller-data"})
        self.assertTrue(malformed["partial"])
        self.assertEqual(malformed["data"], {})
        self.assertNotIn("private-controller-data", repr(malformed))

    def test_rejects_non_object_and_oversized_input(self) -> None:
        for value in (None, [], "not-an-object", {f"k{i}": i for i in range(33)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(RoamingSettingsError):
                project_roaming_settings(value)
        with self.assertRaises(RoamingSettingsError):
            project_roaming_settings({"roaming": {f"k{i}": True for i in range(33)}})


if __name__ == "__main__":
    unittest.main()
