"""Redacted projection of the controller's existing WLAN optimization detail."""
from __future__ import annotations


class RfPlanningDetailError(ValueError):
    """The result is malformed or exceeds the documented limits."""

    def __init__(self, code: str = "rf_planning_detail_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 24
_MAX_APS = 128
_MAX_KEY_LENGTH = 128
_INT64_MAX = 2**63 - 1
_INT32_MAX = 2**31 - 1
_SETTINGS = {
    "channelDeployEnable": "channel_deploy_enabled",
    "channelWidthDeployEnable": "channel_width_deploy_enabled",
    "bandDeployEnable": "band_deploy_enabled",
    "powerAdjustEnable": "power_adjust_enabled",
    "currentConfig": "current_config",
    "successDevices": "success_device_count",
    "failDevices": "failed_device_count",
}
_RADIOS = ("radio2g", "radio5g", "radio5g2", "radio6g")
_RADIO_INT_FIELDS = ("origPower", "rcmdPower", "origBand", "rcmdBand", "errCode")
_RADIO_TEXT_FIELDS = ("origChan", "rcmdChan", "origChanWidth", "rcmdChanWidth")
_AP_FIELDS = {"optimizeSuccess", "support5g2", *_RADIOS, "name", "model", "modelVersion",
              "type", "ip", "failMsg", "failMsgType", "triggerReason"}


def _check_keys(raw: dict[object, object]) -> None:
    if len(raw) > _MAX_FIELDS or any(not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH
                                     for key in raw):
        raise RfPlanningDetailError()


def _project_radio(raw: object, missing: list[str], omitted: set[str],
                   omitted_count: list[int], label: str) -> dict[str, object] | None:
    if raw is None:
        missing.append(label)
        return None
    if not isinstance(raw, dict):
        omitted.add("invalid_radios")
        omitted_count[0] += 1
        return None
    _check_keys(raw)
    result: dict[str, object] = {}
    for name in _RADIO_TEXT_FIELDS:
        if name in raw:
            value = raw[name]
            if isinstance(value, str) and len(value) <= 64:
                result[_snake(name)] = value
            else:
                omitted.add("invalid_radio_values")
                omitted_count[0] += 1
        else:
            missing.append(label + "." + name)
    for name in _RADIO_INT_FIELDS:
        if name in raw:
            value = raw[name]
            if type(value) is int and -_INT32_MAX <= value <= _INT32_MAX:
                result[_snake(name)] = value
            else:
                omitted.add("invalid_radio_values")
                omitted_count[0] += 1
        else:
            missing.append(label + "." + name)
    extras = sum(1 for key in raw if key not in {*_RADIO_TEXT_FIELDS, *_RADIO_INT_FIELDS})
    if extras:
        omitted.add("unknown_fields")
        omitted_count[0] += extras
    return result


def _snake(value: str) -> str:
    out: list[str] = []
    for char in value:
        if char.isupper():
            out.extend(("_", char.lower()))
        else:
            out.append(char)
    return "".join(out).lstrip("_")


def project_rf_planning_detail(raw: object) -> dict[str, object]:
    """Keep optimization configuration and radio deltas, redact AP identity."""
    if not isinstance(raw, dict):
        raise RfPlanningDetailError()
    _check_keys(raw)
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = [0]
    data: dict[str, object] = {}
    for source, target in _SETTINGS.items():
        if source not in raw:
            missing.append(source)
            continue
        value = raw[source]
        if source.endswith("Enable"):
            valid = type(value) is bool
        elif source == "currentConfig":
            valid = type(value) is int and value in (0, 1, 2)
        else:
            valid = type(value) is int and 0 <= value <= _INT32_MAX
        if valid:
            data[target] = value
        else:
            omitted.add("invalid_settings")
            omitted_count[0] += 1

    if "time" not in raw:
        missing.append("time")
    elif type(raw["time"]) is int and 0 <= raw["time"] <= _INT64_MAX:
        data["time_ms"] = raw["time"]
    else:
        omitted.add("invalid_timestamp")
        omitted_count[0] += 1

    if "data" not in raw:
        missing.append("data")
    elif not isinstance(raw["data"], list):
        omitted.add("invalid_ap_details")
        omitted_count[0] += 1
    else:
        aps = raw["data"]
        if len(aps) > _MAX_APS:
            raise RfPlanningDetailError()
        rows: list[dict[str, object]] = []
        for index, ap in enumerate(aps):
            if not isinstance(ap, dict):
                omitted.add("invalid_ap_details")
                omitted_count[0] += 1
                continue
            _check_keys(ap)
            projected: dict[str, object] = {}
            for source, target, kind in (("optimizeSuccess", "optimize_success", "bool"),
                                         ("support5g2", "supports_5g2", "bool"),
                                         ("failMsgType", "failure_type", "int"),
                                         ("triggerReason", "trigger_reason", "int")):
                if source not in ap:
                    missing.append(f"data[{index}].{source}")
                    continue
                value = ap[source]
                valid = type(value) is bool if kind == "bool" else (
                    type(value) is int and -_INT32_MAX <= value <= _INT32_MAX)
                if valid:
                    projected[target] = value
                else:
                    omitted.add("invalid_ap_values")
                    omitted_count[0] += 1
            for radio in _RADIOS:
                if radio not in ap:
                    missing.append(f"data[{index}].{radio}")
                    continue
                value = _project_radio(ap[radio], missing, omitted, omitted_count,
                                       f"data[{index}].{radio}")
                if value is not None:
                    projected[_snake(radio)] = value
            extras = sum(1 for key in ap if key not in _AP_FIELDS)
            if extras:
                omitted.add("unknown_fields")
                omitted_count[0] += extras
            rows.append(projected)
        data["aps"] = rows
        data["ap_count"] = len(rows)

    known = {*_SETTINGS, "time", "data"}
    extras = sum(1 for key in raw if key not in known)
    if extras:
        omitted.add("unknown_fields")
        omitted_count[0] += extras
    return {
        "status": "ok",
        "resource": "rf_planning_detail",
        "data": data,
        "partial": bool(missing or omitted_count[0]),
        "missing_fields": missing,
        "omitted_field_count": omitted_count[0],
        "omitted_fields": sorted(omitted),
    }
