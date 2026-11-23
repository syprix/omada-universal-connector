"""Redacted summary of LTE WAN configuration and documented modem states."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping


class SiteLteWanConfigError(ValueError):
    pass


_ROW_FIELDS = frozenset((
    "portUuId", "portDescription", "portName", "simCardUsed", "status", "cardStatus",
    "simPriority", "mobileData", "dataRoaming", "networkMode", "bandMode", "bands",
    "bands5g", "dialupSetting", "failoverTimeout", "dataRoaming2", "networkMode2",
    "bandMode2", "bands2", "bands5g2", "dialupSetting2", "failoverTimeout2",
    "supportNetworkMode",
))
_DIALUP_FIELDS = frozenset(("networkSearch", "isp", "ispNum", "apnMode", "apn"))


def _code_counts() -> dict[str, int]:
    return {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0,
            "unknown": 0}


def _flag_counts() -> dict[str, int]:
    return {"enabled": 0, "disabled": 0, "unreported": 0}


def summarize_site_lte_wan_config(value: object, *, max_items: int = 1000) -> dict[str, object]:
    if (not isinstance(value, Mapping) or len(value) > 32 or
            type(max_items) is not int or not 1 <= max_items <= 10_000):
        raise SiteLteWanConfigError("invalid LTE WAN response")

    rows = value.get("lteWanPortsConfig")
    if rows is None and "lteWanPortsConfig" not in value:
        rows = []
        missing_field_count = 1
    elif not isinstance(rows, list) or len(rows) > 10_000:
        raise SiteLteWanConfigError("invalid LTE WAN configuration list")
    else:
        missing_field_count = 0
    selected = rows[:max_items]
    enabled = {"mobile_data": _flag_counts(), "data_roaming_sim1": _flag_counts(),
               "data_roaming_sim2": _flag_counts()}
    status_counts = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "unknown": 0}
    card_status_counts = _code_counts()
    network_modes = {"sim1": _code_counts(), "sim2": _code_counts()}
    band_modes = {"sim1": {"0": 0, "1": 0, "unknown": 0},
                  "sim2": {"0": 0, "1": 0, "unknown": 0}}
    network_search_modes = {"sim1": {"0": 0, "1": 0, "unknown": 0},
                            "sim2": {"0": 0, "1": 0, "unknown": 0}}
    apn_modes = {"sim1": {"0": 0, "1": 0, "unknown": 0},
                 "sim2": {"0": 0, "1": 0, "unknown": 0}}
    failover_timeout_configured = {"sim1": 0, "sim2": 0, "unreported": 0}
    selected_band_entry_count = {"sim1": 0, "sim2": 0, "unreported": 0}
    supported_modes: Counter[str] = Counter()
    invalid_record_count = invalid_field_count = unknown_field_count = 0

    def count_code(target: dict[str, int], raw: object, allowed: set[int]) -> None:
        if type(raw) is int and raw in allowed:
            target[str(raw)] += 1
        else:
            target["unknown"] += 1

    def count_flag(target: dict[str, int], raw: object) -> None:
        if type(raw) is bool:
            target["enabled" if raw else "disabled"] += 1
        else:
            target["unreported"] += 1

    for row in selected:
        if not isinstance(row, Mapping) or len(row) > 64:
            invalid_record_count += 1
            for counts in enabled.values():
                counts["unreported"] += 1
            status_counts["unknown"] += 1
            card_status_counts["unknown"] += 1
            for group in (network_modes, band_modes, network_search_modes, apn_modes):
                for counts in group.values():
                    counts["unknown"] += 1
            failover_timeout_configured["unreported"] += 2
            selected_band_entry_count["unreported"] += 2
            continue

        unknown_field_count += sum(field not in _ROW_FIELDS for field in row)
        missing_field_count += sum(field not in row for field in (
            "portUuId", "mobileData", "dataRoaming", "networkMode", "dialupSetting"))
        for target, source in (("mobile_data", "mobileData"),
                               ("data_roaming_sim1", "dataRoaming"),
                               ("data_roaming_sim2", "dataRoaming2")):
            count_flag(enabled[target], row.get(source))
            if source in row and row[source] is not None and type(row[source]) is not bool:
                invalid_field_count += 1
        count_code(status_counts, row.get("status"), {0, 1, 2, 3, 4})
        count_code(card_status_counts, row.get("cardStatus"), set(range(7)))
        count_code(network_modes["sim1"], row.get("networkMode"), set(range(1, 7)))
        count_code(network_modes["sim2"], row.get("networkMode2"), set(range(1, 7)))
        count_code(band_modes["sim1"], row.get("bandMode"), {0, 1})
        count_code(band_modes["sim2"], row.get("bandMode2"), {0, 1})

        for slot, source in (("sim1", "dialupSetting"), ("sim2", "dialupSetting2")):
            setting = row.get(source)
            if setting is None:
                network_search_modes[slot]["unknown"] += 1
                apn_modes[slot]["unknown"] += 1
                unknown_field_count += 1 if source in row else 0
            elif not isinstance(setting, Mapping) or len(setting) > 16:
                invalid_field_count += 1
                network_search_modes[slot]["unknown"] += 1
                apn_modes[slot]["unknown"] += 1
            else:
                unknown_field_count += sum(field not in _DIALUP_FIELDS for field in setting)
                count_code(network_search_modes[slot], setting.get("networkSearch"), {0, 1})
                count_code(apn_modes[slot], setting.get("apnMode"), {0, 1})

        for slot, source in (("sim1", "failoverTimeout"), ("sim2", "failoverTimeout2")):
            timeout = row.get(source)
            if type(timeout) is int and 100 <= timeout <= 3552:
                failover_timeout_configured[slot] += 1
            elif source not in row or timeout is None:
                failover_timeout_configured["unreported"] += 1
            else:
                invalid_field_count += 1
                failover_timeout_configured["unreported"] += 1

        for slot, names in (("sim1", ("bands", "bands5g")),
                            ("sim2", ("bands2", "bands5g2"))):
            reported = False
            for source in names:
                if source not in row or row[source] is None:
                    continue
                reported = True
                values = row[source]
                if not isinstance(values, list) or len(values) > 128 or any(
                        not isinstance(item, str) or len(item) > 32 for item in values):
                    invalid_field_count += 1
                else:
                    selected_band_entry_count[slot] += len(values)
            if not reported:
                selected_band_entry_count["unreported"] += 1

        supported = row.get("supportNetworkMode")
        if supported is not None:
            if (not isinstance(supported, list) or len(supported) > 16 or
                    any(type(code) is not int for code in supported)):
                invalid_field_count += 1
            else:
                for code in supported:
                    supported_modes[str(code) if code in range(1, 7) else "unknown"] += 1

    unknown_field_count += sum(field not in {"portUuid", "portName", "portDesc",
                                               "lteWanPortsConfig"} for field in value)
    if "portUuid" not in value:
        missing_field_count += 1
    unknown_code_count = sum(counts.get("unknown", 0)
                             for counts in (status_counts, card_status_counts,
                                            *network_modes.values(), *band_modes.values(),
                                            *network_search_modes.values(), *apn_modes.values()))
    unknown_code_count += supported_modes.get("unknown", 0)
    unreported_count = sum(counts.get("unreported", 0) for counts in enabled.values())
    unreported_count += failover_timeout_configured["unreported"]
    unreported_count += selected_band_entry_count["unreported"]

    return {
        "resource": "site_lte_wan_config_summary",
        "reported_lte_port_config_count": len(rows),
        "returned_lte_port_config_count": len(selected),
        "configured_flags": enabled,
        "network_mode_code_counts": network_modes,
        "band_mode_code_counts": band_modes,
        "network_search_mode_code_counts": network_search_modes,
        "apn_mode_code_counts": apn_modes,
        "failover_timeout_configured_count": failover_timeout_configured,
        "manual_band_entry_counts": selected_band_entry_count,
        "supported_network_mode_code_counts": dict(sorted(supported_modes.items())),
        "documented_modem_status_code_counts": status_counts,
        "documented_sim_card_status_code_counts": card_status_counts,
        "missing_field_count": missing_field_count,
        "unknown_documented_code_count": unknown_code_count,
        "unreported_optional_value_count": unreported_count,
        "invalid_record_count": invalid_record_count,
        "invalid_field_count": invalid_field_count,
        "unknown_field_count": unknown_field_count,
        "truncated": len(rows) > max_items,
        "partial": bool(missing_field_count or invalid_record_count or invalid_field_count
                         or unknown_field_count or unknown_code_count or unreported_count
                         or len(rows) > max_items),
    }
