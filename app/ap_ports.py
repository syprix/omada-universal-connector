"""Redacted aggregate projection for an access point's Ethernet ports."""
from __future__ import annotations


class ApPortsError(ValueError):
    """Input is outside the documented AP port response bounds."""


_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAX_ROWS = 128
_KNOWN_FIELDS = frozenset({
    "id", "onuId", "port", "portType", "lanPort", "name", "linkStatus",
    "linkSpeed", "duplex", "supportVlan", "localVlanEnable", "localVlanId",
    "localVlanNetworkId", "status", "supportPoe", "poeOutEnable", "poeState",
    "voipState", "supportVlanOption", "supportVlanTagged", "supportStatusEnable",
    "supportStatusInform", "custom", "tagged", "untagged", "taggedNetworkId",
    "untaggedNetworkId", "uplinkPort", "logicUplinkPort", "supportBandwidthControl",
    "bandwidthControlEnable", "ingressRateLimit", "egressRateLimit", "portStatus",
    "poeInputMode",
})


def summarize_ap_ports(rows: object) -> dict[str, object]:
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise ApPortsError()
    link_status: dict[int, int] = {}
    link_speed: dict[int, int] = {}
    port_type: dict[int, int] = {}
    duplex: dict[int, int] = {}
    poe_state: dict[int, int] = {}
    poe_input_mode: dict[int, int] = {}
    counts = {
        "poe_supported_ports": 0,
        "poe_output_enabled_ports": 0,
        "uplink_ports": 0,
        "logical_uplink_ports": 0,
        "vlan_supported_ports": 0,
        "local_vlan_enabled_ports": 0,
    }
    invalid_field_count = 0
    unknown_field_count = 0
    unknown_row_count = 0

    def bump(target: dict[int, int], code: object, allowed: set[int] | None = None) -> bool:
        if type(code) is not int or not _INT32_MIN <= code <= _INT32_MAX or (allowed and code not in allowed):
            return False
        target[code] = target.get(code, 0) + 1
        return True

    for row in rows:
        if not isinstance(row, dict) or len(row) > 64:
            unknown_row_count += 1
            continue
        unknown_field_count += sum(1 for key in row if key not in _KNOWN_FIELDS)
        if "linkStatus" in row and not bump(link_status, row["linkStatus"], {0, 1}):
            invalid_field_count += 1
        if "linkSpeed" in row and not bump(link_speed, row["linkSpeed"], {1, 2, 3, 4}):
            invalid_field_count += 1
        if "portType" in row and not bump(port_type, row["portType"]):
            invalid_field_count += 1
        if "duplex" in row and not bump(duplex, row["duplex"], {1, 2}):
            invalid_field_count += 1
        for field, target in (("poeState", poe_state), ("poeInputMode", poe_input_mode)):
            if field in row:
                allowed = {0, 1} if field == "poeState" else {0, 1, 2, 3}
                if not bump(target, row[field], allowed):
                    invalid_field_count += 1
        bool_fields = {
            "supportPoe": "poe_supported_ports",
            "poeOutEnable": "poe_output_enabled_ports",
            "uplinkPort": "uplink_ports",
            "logicUplinkPort": "logical_uplink_ports",
            "supportVlan": "vlan_supported_ports",
            "localVlanEnable": "local_vlan_enabled_ports",
        }
        for field, count_name in bool_fields.items():
            value = row.get(field)
            if field in row:
                if type(value) is not bool:
                    invalid_field_count += 1
                else:
                    counts[count_name] += int(value)

    partial = bool(invalid_field_count or unknown_field_count or unknown_row_count)
    return {
        "status": "ok",
        "resource": "ap_ports",
        "count": len(rows),
        "summary": {
            "by_link_status_code": dict(sorted(link_status.items())),
            "by_link_speed_code": dict(sorted(link_speed.items())),
            "by_port_type_code": dict(sorted(port_type.items())),
            "duplex_code_counts": dict(sorted(duplex.items())),
            **counts,
            "poe_state_code_counts": dict(sorted(poe_state.items())),
            "poe_input_mode_code_counts": dict(sorted(poe_input_mode.items())),
            "unknown_row_count": unknown_row_count,
            "invalid_field_count": invalid_field_count,
            "unknown_field_count": unknown_field_count,
        },
        "partial": partial,
    }
