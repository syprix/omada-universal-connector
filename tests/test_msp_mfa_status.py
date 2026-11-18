import unittest

from app.msp_mfa_status import MspMfaStatusError, project_msp_mfa_status


class MspMfaStatusTests(unittest.TestCase):
    def test_projects_only_the_documented_enable_switch(self):
        self.assertEqual(project_msp_mfa_status({"enable": False}), {
            "data": {"enabled": False, "invalid_count": 0,
                     "unknown_field_count": 0}, "partial": False,
        })
        result = project_msp_mfa_status({"enable": "on", "secret": "hidden"})
        self.assertIsNone(result["data"]["enabled"])
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("hidden", str(result))

    def test_rejects_unbounded_shapes(self):
        with self.assertRaises(MspMfaStatusError):
            project_msp_mfa_status([])
