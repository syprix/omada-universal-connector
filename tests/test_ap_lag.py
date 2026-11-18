from __future__ import annotations

import unittest

from app.ap_lag import ApLagError, project_ap_lag


FIELDS = ("supportTrunkSetting", "enable", "mode")


class ApLagProjectionTests(unittest.TestCase):
    def test_projects_exact_boolean_and_mode_values(self) -> None:
        for mode in (0, 1, 2):
            raw = {"supportTrunkSetting": True, "enable": False, "mode": mode}
            with self.subTest(mode=mode):
                self.assertEqual(project_ap_lag(raw), {
                    "status": "ok", "resource": "ap_lag", "data": raw,
                    "partial": False, "missing_fields": [], "invalid_fields": [],
                    "unknown_field_count": 0,
                })

    def test_missing_fields_are_partial_without_invented_values(self) -> None:
        result = project_ap_lag({"enable": True})
        self.assertEqual(result["data"], {"enable": True})
        self.assertEqual(result["missing_fields"], ["supportTrunkSetting", "mode"])
        self.assertTrue(result["partial"])

    def test_invalid_booleans_and_mode_are_omitted(self) -> None:
        cases = (
            ({"supportTrunkSetting": 1, "enable": True, "mode": 1}, "supportTrunkSetting"),
            ({"supportTrunkSetting": True, "enable": 0, "mode": 2}, "enable"),
            ({"supportTrunkSetting": True, "enable": False, "mode": True}, "mode"),
            ({"supportTrunkSetting": True, "enable": False, "mode": 3}, "mode"),
            ({"supportTrunkSetting": True, "enable": False, "mode": 2**31}, "mode"),
        )
        for raw, invalid_field in cases:
            with self.subTest(raw=raw):
                result = project_ap_lag(raw)
                self.assertTrue(result["partial"])
                self.assertNotIn(invalid_field, result["data"])
                self.assertEqual(result["invalid_fields"], [invalid_field])

    def test_unknown_fields_are_partial_but_private_values_are_not_returned(self) -> None:
        raw = {"supportTrunkSetting": True, "enable": False, "mode": 0,
               "privateDeviceName": "ap-secret-name", "privateIp": "192.0.2.51"}
        result = project_ap_lag(raw)
        self.assertEqual(result["data"], {key: raw[key] for key in FIELDS})
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertTrue(result["partial"])
        for secret in ("privateDeviceName", "ap-secret-name", "privateIp", "192.0.2.51"):
            self.assertNotIn(secret, repr(result))

    def test_non_object_and_unbounded_inputs_fail_closed(self) -> None:
        for raw in (None, [], "raw", {"x" * 129: True}, {index: False for index in range(1)}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ApLagError):
                project_ap_lag(raw)
        with self.assertRaises(ApLagError):
            project_ap_lag({f"unknown-{i}": i for i in range(17)})

    def test_reported_support_flag_is_not_reinterpreted(self) -> None:
        result = project_ap_lag({"supportTrunkSetting": False, "enable": True, "mode": 2})
        self.assertEqual(result["data"], {"supportTrunkSetting": False, "enable": True, "mode": 2})
        self.assertNotIn("hardware_supported", result)
        self.assertNotIn("firmware_supported", result)


if __name__ == "__main__":
    unittest.main()
