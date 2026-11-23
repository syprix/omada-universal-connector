from __future__ import annotations

import unittest

from app.gateway_sim_sms_support import (
    GatewaySimSupportError, project_gateway_sim_support,
)


class GatewaySimSupportTests(unittest.TestCase):
    def test_projects_documented_fields_and_keeps_unmapped_dual_sim_unknown(self):
        result = project_gateway_sim_support({
            "errorCode": 0,
            "msg": "",
            "result": {"supportSms": True, "supportLte": False,
                       "supportDualSms": 2, "supportDualSim": 0},
        })
        self.assertEqual(result, {
            "sim_sms_supported": True,
            "lte_supported": False,
            "dual_sms_supported_sim_count": 1,
            "dual_sms_state": "known",
            "dual_sim_capability": "unknown",
            "dual_sim_source_value_present": True,
        })
        self.assertNotIn("supportDualSim", str(result))

    def test_missing_fields_remain_unknown(self):
        result = project_gateway_sim_support({"errorCode": 0, "msg": "", "result": {}})
        self.assertIsNone(result["sim_sms_supported"])
        self.assertIsNone(result["lte_supported"])
        self.assertIsNone(result["dual_sms_supported_sim_count"])
        self.assertEqual(result["dual_sms_state"], "unknown")
        self.assertFalse(result["dual_sim_source_value_present"])

    def test_rejects_undocumented_fields_and_invalid_scalars(self):
        payloads = (
            {"errorCode": 0, "msg": "", "result": {"simId": "secret"}},
            {"errorCode": 0, "msg": "", "result": {"supportSms": 1}},
            {"errorCode": 0, "msg": "", "result": {"supportDualSms": 4}},
            {"errorCode": -1, "msg": "", "result": {}},
            {"errorCode": 0, "msg": 7, "result": {}},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(GatewaySimSupportError):
                    project_gateway_sim_support(payload)


if __name__ == "__main__":
    unittest.main()
