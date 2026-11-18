import unittest

from app.msp_license_auto_active import (
    MspLicenseAutoActiveError, project_msp_license_auto_active,
)


class MspLicenseAutoActiveTests(unittest.TestCase):
    def test_projects_only_documented_boolean(self):
        self.assertEqual(project_msp_license_auto_active({"autoActive": False}), {
            "data": {"enabled": False, "invalid_count": 0,
                     "unknown_field_count": 0}, "partial": False,
        })
        result = project_msp_license_auto_active({"autoActive": "yes", "secret": "hidden"})
        self.assertIsNone(result["data"]["enabled"])
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("hidden", str(result))

    def test_rejects_invalid_shape(self):
        with self.assertRaises(MspLicenseAutoActiveError):
            project_msp_license_auto_active([])
