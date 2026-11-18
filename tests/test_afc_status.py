from __future__ import annotations

import unittest

from app.afc_status import AfcStatusError, project_afc_status


class AfcStatusProjectionTests(unittest.TestCase):
    def test_projects_all_documented_values_without_unit_conversion(self) -> None:
        payload = {
            "status": True,
            "lastResponse": False,
            "processing": True,
            "available6g": False,
            "expirationTimeSec": 1_700_000_000,
            "lastResponseTimeSec": 1_600_000_000,
            "errCode": -20,
            "errMain": 3,
            "errDetail": -4,
        }
        result = project_afc_status(payload)
        self.assertEqual(result["data"], payload)
        self.assertFalse(result["partial"])
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(result["omitted_field_count"], 0)
        self.assertEqual(result["omitted_fields"], [])

    def test_signed_integer_schema_bounds_are_enforced(self) -> None:
        result = project_afc_status({
            "expirationTimeSec": -(2**63),
            "lastResponseTimeSec": 2**63 - 1,
            "errCode": -(2**31),
            "errMain": 2**31 - 1,
        })
        self.assertEqual(result["data"], {
            "expirationTimeSec": -(2**63), "lastResponseTimeSec": 2**63 - 1,
            "errCode": -(2**31), "errMain": 2**31 - 1,
        })
        self.assertTrue(result["partial"])

    def test_missing_and_wrongly_typed_values_are_partial_and_not_echoed(self) -> None:
        result = project_afc_status({
            "status": 1,
            "lastResponse": "private-text",
            "expirationTimeSec": True,
            "errCode": 2**31,
            "privateFieldName": "private-value",
        })
        self.assertEqual(result["data"], {})
        self.assertTrue(result["partial"])
        self.assertIn("status", result["omitted_fields"])
        self.assertIn("lastResponse", result["omitted_fields"])
        self.assertIn("expirationTimeSec", result["omitted_fields"])
        self.assertIn("errCode", result["omitted_fields"])
        self.assertIn("unknown_fields", result["omitted_fields"])
        rendered = repr(result)
        for private in ("privateFieldName", "private-value", "private-text"):
            self.assertNotIn(private, rendered)

    def test_empty_object_is_partial_because_all_documented_values_are_missing(self) -> None:
        result = project_afc_status({})
        self.assertTrue(result["partial"])
        self.assertEqual(len(result["missing_fields"]), 9)
        self.assertEqual(result["omitted_field_count"], 9)

    def test_unknown_values_are_counted_but_never_exposed(self) -> None:
        result = project_afc_status({
            "status": True,
            "details": {"name": "secret", "ip": "192.0.2.1"},
            "siteId": "raw-site-id",
        })
        rendered = repr(result)
        for private in ("details", "secret", "192.0.2.1", "siteId", "raw-site-id"):
            self.assertNotIn(private, rendered)
        self.assertEqual(result["omitted_field_count"], 10)
        self.assertEqual(result["omitted_fields"], ["unknown_fields"])

    def test_rejects_non_objects_and_oversized_input(self) -> None:
        for payload in (None, [], "not-object", {f"extra{i}": i for i in range(33)}):
            with self.subTest(payload_type=type(payload).__name__), self.assertRaises(AfcStatusError):
                project_afc_status(payload)


if __name__ == "__main__":
    unittest.main()
