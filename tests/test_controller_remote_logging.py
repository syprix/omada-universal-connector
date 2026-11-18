import unittest

from app.controller_remote_logging import (
    ControllerRemoteLoggingError,
    project_controller_remote_logging,
)


class ControllerRemoteLoggingTests(unittest.TestCase):
    def test_projects_state_and_presence_without_network_target(self):
        result = project_controller_remote_logging({
            "enable": True, "host": "logs.example.com", "port": 6514,
        })
        self.assertEqual(result["data"]["settings"], {
            "enabled": True, "host_present": True, "port_present": True,
        })
        self.assertNotIn("logs.example.com", str(result))
        self.assertNotIn("6514", str(result))
        self.assertFalse(result["partial"])

    def test_invalid_and_unknown_fields_are_excluded_and_partial(self):
        result = project_controller_remote_logging({
            "enable": 1, "host": "bad host", "port": 70000,
            "secret": "do-not-return",
        })
        self.assertEqual(result["data"]["settings"], {
            "host_present": False, "port_present": False,
        })
        self.assertEqual(result["data"]["invalid_count"], 3)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("do-not-return", str(result))
        self.assertTrue(result["partial"])

    def test_required_enable_and_response_limits_are_enforced(self):
        missing = project_controller_remote_logging({"host": "logs.example.com"})
        self.assertEqual(missing["data"]["missing_required_count"], 1)
        self.assertTrue(missing["partial"])
        with self.assertRaisesRegex(ControllerRemoteLoggingError, "response_invalid"):
            project_controller_remote_logging(None)
        with self.assertRaisesRegex(ControllerRemoteLoggingError, "response_invalid"):
            project_controller_remote_logging({str(i): False for i in range(17)})


if __name__ == "__main__":
    unittest.main()
