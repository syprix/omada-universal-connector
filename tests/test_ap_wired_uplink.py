from __future__ import annotations

import math
import unittest

from app.ap_wired_uplink import ApWiredUplinkError, project_ap_wired_uplink


I32_MIN, I32_MAX = -(2**31), 2**31 - 1
I64_MIN, I64_MAX = -(2**63), 2**63 - 1


def complete_info() -> dict[str, object]:
    return {
        "duplex": 2,
        "portType": 2,
        "upBytes": 0,
        "downBytes": I64_MAX,
        "upPackets": 100,
        "downPackets": I64_MIN,
        "upDropPackets": 0,
        "downDropPackets": 2,
        "upErrorsPackets": 0,
        "downErrorsPackets": 1,
        "activity": 42,
        "linkStatus": I32_MIN,
        "linkSpeed": I32_MAX,
    }


class ApWiredUplinkProjectionTests(unittest.TestCase):
    def test_optional_inventory_reference_redacts_and_maps_the_upstream_mac(self) -> None:
        ref = "a" * 24
        info = complete_info()
        info["uplinkMac"] = "00:11:22:33:44:55"
        projected = project_ap_wired_uplink(
            {"wiredUplink": info},
            device_ref_by_mac={"001122334455": ref})
        data = projected["data"]["wiredUplink"]
        self.assertEqual(data["uplink_device_ref"], ref)
        self.assertEqual(data["uplink_device_ref_status"], "mapped")
        self.assertNotIn("00:11:22:33:44:55", repr(projected))

    def test_projects_documented_core_fields_as_reported(self) -> None:
        raw = {"wiredUplink": complete_info()}
        result = project_ap_wired_uplink(raw)
        self.assertEqual(result["data"], raw)
        self.assertFalse(result["partial"])
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(result["invalid_fields"], [])

    def test_int32_and_int64_boundaries_and_bool_rejection(self) -> None:
        info = complete_info()
        info["duplex"] = 0
        info["portType"] = 0
        info["upBytes"] = I64_MIN
        info["linkStatus"] = I32_MAX
        result = project_ap_wired_uplink({"wiredUplink": info})
        self.assertFalse(result["partial"])
        for field, value in (("duplex", -1), ("duplex", 3), ("duplex", True),
                             ("portType", 3), ("portType", False),
                             ("upBytes", I64_MAX + 1), ("activity", I64_MIN - 1),
                             ("upPackets", True), ("linkSpeed", I32_MAX + 1),
                             ("linkStatus", False)):
            with self.subTest(field=field, value=value):
                changed = complete_info()
                changed[field] = value
                projected = project_ap_wired_uplink({"wiredUplink": changed})
                self.assertTrue(projected["partial"])
                self.assertIn("wiredUplink." + field, projected["invalid_fields"])
                self.assertNotIn(field, projected["data"]["wiredUplink"])

    def test_optional_poe_and_voip_are_enum_checked_but_may_be_absent(self) -> None:
        result = project_ap_wired_uplink({"wiredUplink": complete_info()})
        self.assertFalse(result["partial"])
        for field in ("poeState", "voipState"):
            for value in (0, 1):
                info = complete_info()
                info[field] = value
                self.assertEqual(project_ap_wired_uplink({"wiredUplink": info})["data"]["wiredUplink"][field], value)
            for value in (2, True, -1):
                info = complete_info()
                info[field] = value
                result = project_ap_wired_uplink({"wiredUplink": info})
                self.assertIn("wiredUplink." + field, result["invalid_fields"])
                self.assertTrue(result["partial"])

    def test_rate_only_accepts_exact_documented_strings_and_normalizes_to_number(self) -> None:
        for value in ("0", "10", "100", "1000", "2500", "10000"):
            with self.subTest(value=value):
                info = complete_info()
                info["rate"] = value
                result = project_ap_wired_uplink({"wiredUplink": info})
                self.assertEqual(result["data"]["wiredUplink"]["rate_mbps"], int(value))
                self.assertNotIn("rate", result["data"]["wiredUplink"])
                self.assertFalse(result["partial"])
        for value in (0, "01", "10000.0", "250", "1000 Mbps", None):
            info = complete_info()
            info["rate"] = value
            result = project_ap_wired_uplink({"wiredUplink": info})
            self.assertIn("wiredUplink.rate", result["invalid_fields"])
            self.assertTrue(result["partial"])

    def test_optional_sensor_numbers_are_finite_numeric_values_without_units(self) -> None:
        info = complete_info()
        for name, value in (("txPower", 1.25), ("rxPower", -2),
                            ("temp", 0.0), ("voltage", 3), ("current", 0.0)):
            info[name] = value
        result = project_ap_wired_uplink({"wiredUplink": info})
        for name in ("txPower", "rxPower", "temp", "voltage", "current"):
            self.assertEqual(result["data"]["wiredUplink"][name], info[name])
        self.assertFalse(result["partial"])
        for bad in (True, "1.2", float("nan"), float("inf"), -(10**1000)):
            info = complete_info()
            info["txPower"] = bad
            result = project_ap_wired_uplink({"wiredUplink": info})
            self.assertTrue(result["partial"])
            self.assertIn("wiredUplink.txPower", result["invalid_fields"])
            self.assertNotIn("txPower", result["data"]["wiredUplink"])

    def test_missing_core_fields_partial_but_missing_optional_metrics_are_not(self) -> None:
        result = project_ap_wired_uplink({"wiredUplink": complete_info()})
        self.assertFalse(result["partial"])
        info = complete_info()
        del info["activity"]
        result = project_ap_wired_uplink({"wiredUplink": info})
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_fields"], ["wiredUplink.activity"])
        self.assertNotIn("activity", result["data"]["wiredUplink"])

    def test_missing_or_empty_safe_uplink_is_unknown_incomplete(self) -> None:
        for raw in ({}, {"wiredUplink": {}}, {"wiredUplink": {
                "name": "private-name", "uplinkMac": "private-mac"}}):
            with self.subTest(keys=list(raw)):
                result = project_ap_wired_uplink(raw)
                self.assertTrue(result["partial"])
                self.assertTrue(result["missing_fields"])
                self.assertNotIn("private-name", repr(result))
                self.assertNotIn("private-mac", repr(result))

    def test_all_documented_identity_fields_are_redacted(self) -> None:
        identifiers = {
            "uplinkMac": "private-mac", "stackId": "private-stack",
            "type": "private-type", "name": "private-name", "port": "port-9",
            "ip": "192.0.2.9", "model": "private-model",
            "modelVersion": "private-version", "uplinkPort": "uplink-3",
        }
        result = project_ap_wired_uplink({"wiredUplink": {**complete_info(), **identifiers}})
        self.assertFalse(result["partial"])
        self.assertEqual(result["redacted_field_count"], len(identifiers))
        for secret in identifiers.values():
            self.assertNotIn(secret, repr(result))

    def test_unknown_fields_mark_partial_without_echoing_names_or_values(self) -> None:
        result = project_ap_wired_uplink({"wiredUplink": {
            **complete_info(), "privateExtension": "private-value"},
            "other": "private-root-value"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 2)
        for secret in ("privateExtension", "private-value", "other", "private-root-value"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_containers_are_partial_and_oversized_structures_fail_closed(self) -> None:
        for value in (None, [], "secret-string", 4):
            result = project_ap_wired_uplink({"wiredUplink": value})
            self.assertTrue(result["partial"])
            self.assertEqual(result["invalid_fields"], ["wiredUplink"])
            self.assertNotIn("secret-string", repr(result))
        for raw in (None, [], {f"x{i}": i for i in range(9)},
                    {"wiredUplink": {**complete_info(), **{f"x{i}": i for i in range(40)}}},
                    {"x" * 129: 1}, {"wiredUplink": list(range(49))}):
            with self.subTest(raw_type=type(raw).__name__):
                with self.assertRaises(ApWiredUplinkError):
                    project_ap_wired_uplink(raw)


if __name__ == "__main__":
    unittest.main()
