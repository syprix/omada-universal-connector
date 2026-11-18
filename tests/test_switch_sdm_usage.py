from __future__ import annotations

import unittest

from app.switch_sdm_usage import SwitchSdmUsageError, project_switch_sdm_usage


class SwitchSdmUsageProjectionTests(unittest.TestCase):
    def test_projects_documented_category_and_entry_count_codes(self) -> None:
        for category in (0, 1, 3, 4):
            with self.subTest(category=category):
                result = project_switch_sdm_usage({"category": category, "num": 32})
                self.assertEqual(result["data"], {"category": category, "num": 32})
                self.assertFalse(result["partial"])

    def test_missing_and_malformed_fields_are_partial_without_coercion(self) -> None:
        result = project_switch_sdm_usage({"category": True, "num": 2**31})
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"], {})
        self.assertEqual(result["omitted_fields"], ["category", "num"])
        missing = project_switch_sdm_usage({"num": 0})
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["missing_fields"], ["category"])

    def test_unknown_fields_are_dropped_and_size_is_bounded(self) -> None:
        result = project_switch_sdm_usage({"category": 0, "num": 2,
                                           "switchMac": "private-mac"})
        self.assertTrue(result["partial"])
        self.assertNotIn("private-mac", repr(result))
        with self.assertRaises(SwitchSdmUsageError):
            project_switch_sdm_usage({"category": 0, "num": 2,
                                      **{f"x{i}": i for i in range(16)}})


if __name__ == "__main__":
    unittest.main()
