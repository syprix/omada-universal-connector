"""Redacted SMS, LTE and SIM capability fields for one inventoried gateway."""
from __future__ import annotations
from collections.abc import Mapping


class GatewaySimSupportError(ValueError):
    pass


def project_gateway_sim_support(payload: object) -> dict[str, object]:
    error_code = payload.get("errorCode") if isinstance(payload, Mapping) else None
    message = payload.get("msg") if isinstance(payload, Mapping) else None
    if (not isinstance(payload, Mapping) or set(payload) - {"errorCode", "msg", "result"} or
            type(error_code) is not int or not -(2**31) <= error_code < 2**31 or error_code != 0 or
            (message is not None and (not isinstance(message, str) or len(message) > 4_096)) or
            not isinstance(payload.get("result"), Mapping)):
        raise GatewaySimSupportError("envelope_invalid")
    result = payload["result"]
    allowed = {"supportSms", "supportLte", "supportDualSms", "supportDualSim"}
    if set(result) - allowed:
        raise GatewaySimSupportError("result_invalid")

    def boolean_field(name: str) -> bool | None:
        value = result.get(name)
        if value is None:
            return None
        if type(value) is not bool:
            raise GatewaySimSupportError("result_invalid")
        return value

    dual_sms = result.get("supportDualSms")
    if dual_sms is not None and (type(dual_sms) is not int or not 0 <= dual_sms <= 3):
        raise GatewaySimSupportError("result_invalid")
    dual_sim = result.get("supportDualSim")
    if dual_sim is not None and (type(dual_sim) is not int or not -(2**31) <= dual_sim < 2**31):
        raise GatewaySimSupportError("result_invalid")

    return {
        "sim_sms_supported": boolean_field("supportSms"),
        "lte_supported": boolean_field("supportLte"),
        "dual_sms_supported_sim_count": ({0: 0, 1: 1, 2: 1, 3: 2}.get(dual_sms)
                                          if dual_sms is not None else None),
        "dual_sms_state": "known" if dual_sms is not None else "unknown",
        "dual_sim_capability": "unknown",
        "dual_sim_source_value_present": dual_sim is not None,
    }
