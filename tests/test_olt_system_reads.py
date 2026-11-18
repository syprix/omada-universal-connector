from __future__ import annotations

import unittest

from app.olt_system_reads import (
    OltSystemReadError, project_olt_management_interfaces, project_olt_system_info,
)


class OltSystemReadProjectionTests(unittest.TestCase):
    """Projection fixtures for olt_system_info and olt_management_interfaces."""

    def test_olt_system_info_keeps_safe_statuses_and_redacts_identity(self) -> None:
        projected = project_olt_system_info({
            "systemDescription": "private description", "deviceName": "private-olt",
            "deviceLocation": "rack 2", "contactInformation": "admin@example.invalid",
            "mac": "00:11:22:33:44:55", "serialNumber": "private-serial",
            "hardwareVersion": "v1", "firmwareVersion": "v2",
            "bootLoaderVersion": "v3", "systemTime": "private time",
            "runningTime": 1200, "jumboFrameStatus": 1, "sntpStatus": 0,
            "igmpSnoopingStatus": 1, "snmpStatus": 0, "spanningTreeStatus": 1,
            "dhcpRelayStatus": 0, "httpServerStatus": 1, "telnetStatus": 0,
            "sshStatus": 1,
        })
        data = projected["data"]
        self.assertEqual(data["uptime_seconds"], 1200)
        self.assertTrue(data["jumbo_frame_enabled"])
        self.assertFalse(data["sntp_enabled"] if "sntp_enabled" in data else data["time_sync_enabled"])
        self.assertFalse(projected["partial"])
        for private in ("private description", "private-olt", "admin@example.invalid",
                        "00:11:22:33:44:55", "private-serial", "private time"):
            self.assertNotIn(private, repr(projected))

    def test_olt_system_info_marks_unknown_and_invalid_fields_partial(self) -> None:
        result = project_olt_system_info({"runningTime": -1, "sshStatus": 2,
                                          "privateExtra": "discard"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("discard", repr(result))
        with self.assertRaises(OltSystemReadError):
            project_olt_system_info([])

    def test_olt_management_interfaces_project_only_categorical_counts(self) -> None:
        projected = project_olt_management_interfaces({"systemInterfaces": [
            {"interfaceId": 0, "interfaceType": "MANAGEMENT", "interfaceValue": "192.0.2.1"},
            {"interfaceId": 1, "interfaceType": "VLAN", "interfaceValue": "private-vlan"},
            {"interfaceId": 2, "interfaceType": "NONE", "interfaceValue": ""},
        ]})
        data = projected["data"]
        self.assertEqual(data["interface_count"], 3)
        self.assertEqual(data["type_counts"], {"MANAGEMENT": 1, "VLAN": 1, "NONE": 1})
        self.assertFalse(projected["partial"])
        for private in ("192.0.2.1", "private-vlan"):
            self.assertNotIn(private, repr(projected))

    def test_olt_management_interfaces_are_bounded_and_invalid_rows_are_counted(self) -> None:
        with self.assertRaises(OltSystemReadError):
            project_olt_management_interfaces({"systemInterfaces": [{}] * 65})
        projected = project_olt_management_interfaces({"systemInterfaces": [
            {"interfaceType": "UNKNOWN", "extra": "discard"}, None,
        ]})
        self.assertTrue(projected["partial"])
        self.assertEqual(projected["invalid_count"], 2)
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertNotIn("discard", repr(projected))


if __name__ == "__main__":
    unittest.main()
