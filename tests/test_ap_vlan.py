from __future__ import annotations

import unittest

from app.ap_vlan import ApVlanError, project_ap_vlan


INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


class ApVlanProjectionTests(unittest.TestCase):
    def test_projects_optional_vlan_settings_without_interpretation(self) -> None:
        raw = {
            "mvlanSetting": {"mode": 1, "bridgeVlan": INT32_MIN},
            "voipVlanSetting": {"mode": 0, "voipBridgeVlan": INT32_MAX, "ipType": 1},
        }
        result = project_ap_vlan(raw)
        self.assertEqual(result["data"], raw)
        self.assertFalse(result["partial"])
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(result["invalid_fields"], [])

    def test_root_settings_are_optional_and_not_filled_in(self) -> None:
        result = project_ap_vlan({})
        self.assertEqual(result["data"], {})
        self.assertFalse(result["partial"])

    def test_present_object_requires_mode(self) -> None:
        for key, value in (("mvlanSetting", {"bridgeVlan": 10}),
                           ("voipVlanSetting", {"ipType": 0})):
            with self.subTest(key=key):
                result = project_ap_vlan({key: value})
                self.assertTrue(result["partial"])
                self.assertEqual(result["missing_fields"], [key + ".mode"])
                self.assertNotIn("mode", result["data"][key])

    def test_enum_values_and_strict_integer_types(self) -> None:
        for key, setting, field in (
            ("mvlanSetting", {"mode": -1}, "mode"),
            ("mvlanSetting", {"mode": 2}, "mode"),
            ("mvlanSetting", {"mode": True}, "mode"),
            ("voipVlanSetting", {"mode": 0, "ipType": -1}, "ipType"),
            ("voipVlanSetting", {"mode": 0, "ipType": 2}, "ipType"),
            ("voipVlanSetting", {"mode": 0, "ipType": False}, "ipType"),
        ):
            with self.subTest(key=key, setting=setting):
                result = project_ap_vlan({key: setting})
                self.assertTrue(result["partial"])
                self.assertIn(f"{key}.{field}", result["invalid_fields"])
                self.assertNotIn(field, result["data"][key])

    def test_optional_vlan_ids_accept_any_int32_but_reject_bool_and_overflow(self) -> None:
        for field in ("bridgeVlan", "voipBridgeVlan"):
            setting_name = "mvlanSetting" if field == "bridgeVlan" else "voipVlanSetting"
            for value in (INT32_MIN, INT32_MAX, -100):
                result = project_ap_vlan({setting_name: {"mode": 0, field: value}})
                self.assertEqual(result["data"][setting_name][field], value)
                self.assertFalse(result["partial"])
            for value in (True, INT32_MIN - 1, INT32_MAX + 1):
                result = project_ap_vlan({setting_name: {"mode": 0, field: value}})
                self.assertIn(f"{setting_name}.{field}", result["invalid_fields"])
                self.assertTrue(result["partial"])

    def test_known_network_identifiers_and_addresses_are_redacted_not_partial(self) -> None:
        secrets = {
            "lanNetworkId": "network-id-secret", "ip": "10.0.0.5",
            "ipMask": "255.255.255.0", "ipGateway": "10.0.0.1",
            "ipDns1": "1.1.1.1", "ipDns2": "8.8.8.8",
        }
        result = project_ap_vlan({"voipVlanSetting": {"mode": 0, **secrets}})
        self.assertEqual(result["data"], {"voipVlanSetting": {"mode": 0}})
        self.assertEqual(result["redacted_field_count"], len(secrets))
        self.assertFalse(result["partial"])
        for secret in secrets.values():
            self.assertNotIn(secret, repr(result))

    def test_ip_fields_in_mvlan_are_unknown_but_still_never_disclosed(self) -> None:
        result = project_ap_vlan({"mvlanSetting": {
            "mode": 0, "ip": "10.0.0.9", "ipMask": "255.255.255.0"}})
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertEqual(result["redacted_field_count"], 0)
        self.assertNotIn("10.0.0.9", repr(result))
        self.assertNotIn("ipMask", repr(result))

    def test_unknown_fields_mark_partial_without_disclosing_values(self) -> None:
        result = project_ap_vlan({"voipVlanSetting": {
            "mode": 1, "vendorExtension": "private-value"},
            "controllerName": "private-controller"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertNotIn("vendorExtension", repr(result))
        self.assertNotIn("private-value", repr(result))
        self.assertNotIn("private-controller", repr(result))

    def test_invalid_setting_container_and_size_limits_fail_closed(self) -> None:
        for raw in (None, [], "raw",
                    {"mvlanSetting": {"mode": 0, **{f"x{i}": i for i in range(16)}}},
                    {f"x{i}": i for i in range(9)}, {"x" * 129: 1}):
            with self.subTest(type=type(raw).__name__, size=(len(raw) if hasattr(raw, "__len__") else None)):
                with self.assertRaises(ApVlanError):
                    project_ap_vlan(raw)

    def test_invalid_optional_setting_container_is_partial(self) -> None:
        for value in (None, ["private-list-sentinel"], "private-string-sentinel", 42):
            with self.subTest(value=type(value).__name__):
                result = project_ap_vlan({"mvlanSetting": value})
                self.assertTrue(result["partial"])
                self.assertEqual(result["invalid_fields"], ["mvlanSetting"])
                self.assertEqual(result["data"], {"mvlanSetting": {}})
                self.assertNotIn("private-", repr(result))
        with self.assertRaises(ApVlanError):
            project_ap_vlan({"mvlanSetting": list(range(17))})


if __name__ == "__main__":
    unittest.main()
