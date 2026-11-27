from __future__ import annotations

import unittest

from app.site_access_control_policy_coverage import (
    MAX_POLICY_ENTRIES,
    MISSING_ACCESS_CONTROL_RESULT,
    SiteAccessControlPolicyCoverageError,
    project_site_access_control_policy_coverage,
)


class NonIterableList(list):
    def __iter__(self):
        raise AssertionError("policy items must not be inspected")


class SiteAccessControlPolicyCoverageTests(unittest.TestCase):
    def test_flags_and_policy_list_counts_do_not_expose_or_iterate_entries(self):
        secret_marker = "private-policy-identity-and-network-value"
        result = project_site_access_control_policy_coverage({
            "preAuthAccessEnable": False,
            "freeAuthClientEnable": True,
            "preAuthAccessPolicies": NonIterableList([secret_marker, {"value": secret_marker}]),
            "freeAuthClientPolicies": [],
        })

        self.assertEqual(result["source_state"], "present")
        self.assertEqual(result["data"], {
            "pre_auth_access_enabled": False,
            "free_auth_client_enabled": True,
        })
        self.assertEqual(result["policy_list_coverage"], {
            "pre_auth_access_policies": {
                "present": True, "form_valid": True, "entry_count": 2,
                "state": "nonempty",
            },
            "free_auth_client_policies": {
                "present": True, "form_valid": True, "entry_count": 0,
                "state": "empty",
            },
        })
        self.assertFalse(result["policy_contents_inspected"])
        self.assertNotIn(secret_marker, repr(result))

    def test_missing_invalid_and_over_limit_lists_are_distinct(self):
        missing = project_site_access_control_policy_coverage({
            "preAuthAccessEnable": True, "freeAuthClientEnable": False,
        })
        self.assertEqual(missing["policy_list_coverage"]["pre_auth_access_policies"], {
            "present": False, "form_valid": None, "entry_count": None,
            "state": "missing",
        })

        invalid = project_site_access_control_policy_coverage({
            "preAuthAccessEnable": True, "freeAuthClientEnable": False,
            "preAuthAccessPolicies": {"not": "a list"},
            "freeAuthClientPolicies": "not a list",
        })
        self.assertEqual(invalid["invalid_field_count"], 2)
        self.assertEqual(invalid["policy_list_coverage"]["pre_auth_access_policies"]["state"],
                         "invalid")

        over_limit = project_site_access_control_policy_coverage({
            "preAuthAccessEnable": True, "freeAuthClientEnable": False,
            "preAuthAccessPolicies": NonIterableList([object()] * (MAX_POLICY_ENTRIES + 1)),
            "freeAuthClientPolicies": [],
        })
        coverage = over_limit["policy_list_coverage"]["pre_auth_access_policies"]
        self.assertEqual(coverage["state"], "over_limit")
        self.assertEqual(coverage["entry_count"], MAX_POLICY_ENTRIES)
        self.assertEqual(over_limit["over_limit_field_count"], 1)

    def test_missing_result_unknown_fields_and_invalid_top_level_are_reported(self):
        missing = project_site_access_control_policy_coverage(MISSING_ACCESS_CONTROL_RESULT)
        self.assertEqual(missing["source_state"], "missing")
        self.assertEqual(missing["missing_field_count"], 4)
        self.assertTrue(missing["partial"])

        unknown = project_site_access_control_policy_coverage({
            "preAuthAccessEnable": True, "freeAuthClientEnable": False,
            "preAuthAccessPolicies": [], "freeAuthClientPolicies": [],
            "private-field-name": "private-value",
        })
        self.assertEqual(unknown["unknown_field_count"], 1)
        self.assertNotIn("private-field-name", repr(unknown))
        self.assertNotIn("private-value", repr(unknown))

        for invalid in (None, [], "invalid", {str(i): i for i in range(17)}):
            with self.subTest(kind=type(invalid).__name__):
                with self.assertRaisesRegex(SiteAccessControlPolicyCoverageError,
                                            "response_invalid"):
                    project_site_access_control_policy_coverage(invalid)


if __name__ == "__main__":
    unittest.main()
