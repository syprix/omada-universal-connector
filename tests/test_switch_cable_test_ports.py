from __future__ import annotations

import unittest

from app.switch_cable_test_ports import SwitchCableTestPortsError, project_switch_cable_test_ports


class SwitchCableTestPortProjectionTests(unittest.TestCase):
    def test_projects_supported_fields_and_drops_private_port_details(self) -> None:
        result = project_switch_cable_test_ports([{
            "port": 7, "standardPort": {"unit": 1, "slot": 2, "port": 7},
            "type": 1, "name": "private-label", "editEnable": True,
            "isUpperPort": False, "isDisabled": False, "isStackPort": False,
            "reasons": [], "downlinkDevices": [{"mac": "private-mac", "ip": "192.0.2.1"}],
            "isCopper": True,
        }])
        self.assertEqual(result["data"]["ports"], [{
            "port": 7, "type_code": 1, "editEnable": True, "upper_port": False,
            "disabled": False, "stack_port": False, "reason_codes": [], "copper": True,
        }])
        self.assertTrue(result["partial"])
        for secret in ("private-label", "private-mac", "192.0.2.1", "unit", "slot"):
            self.assertNotIn(secret, repr(result))

    def test_reports_missing_and_invalid_values(self) -> None:
        result = project_switch_cable_test_ports([{"port": True, "type": "1", "reasons": [-1, 88]}])
        self.assertTrue(result["partial"])
        self.assertNotIn("port", result["data"]["ports"][0])
        self.assertEqual(result["data"]["ports"][0]["reason_codes"], [-1])
        self.assertIn("ports[0].editEnable", result["missing_fields"])

    def test_rejects_oversized_response(self) -> None:
        with self.assertRaises(SwitchCableTestPortsError):
            project_switch_cable_test_ports([{}] * 513)


if __name__ == "__main__":
    unittest.main()
