"""Privacy-preserving summary of site WAN port configuration."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping


class SiteWanPortsError(ValueError):
    """The controller response has an invalid outer shape."""


_TOP = frozenset(("wanPortsConfig", "UsbPortsConfig"))
_WAN = frozenset(("portId", "portName", "portDescription", "wanPortIpv4Setting",
                  "wanPortIpv6Setting", "wanPortMacSetting", "dslSetting"))
_USB = frozenset(("portId", "portDescription", "portName", "usbModem", "reduceUsbRif",
                  "configType", "autoConfig", "manuallyConfig", "connectionMode",
                  "usbModemMsgId", "pin", "authType", "mtuSize", "dnsEnable",
                  "dhcpOptions", "dnsConfig"))


def _code_counts(counter: Counter[int]) -> dict[str, int]:
    return {str(code): count for code, count in sorted(counter.items())}


def project_site_wan_ports(result: object) -> dict[str, object]:
    """Validate documented shapes and return counts/codes, never raw config values."""
    if not isinstance(result, Mapping) or len(result) > 16:
        raise SiteWanPortsError("result must be a bounded object")
    missing = invalid = 0
    unknown = sum(key not in _TOP for key in result)
    ipv4_protocols: Counter[int] = Counter()
    usb_config_types: Counter[int] = Counter()
    usb_connection_modes: Counter[int] = Counter()
    ipv6_enabled = 0
    ipv6_disabled = 0
    dsl_mer_enabled = 0
    dsl_mer_disabled = 0

    wan_rows = result.get("wanPortsConfig")
    if "wanPortsConfig" not in result:
        missing += 1
        wan_rows = []
    elif not isinstance(wan_rows, list) or len(wan_rows) > 256:
        invalid += 1
        wan_rows = []
    valid_wan = 0
    for row in wan_rows:
        if not isinstance(row, Mapping) or len(row) > 32:
            invalid += 1
            continue
        unknown += sum(key not in _WAN for key in row)
        row_valid = True
        for key in ("portId", "wanPortIpv4Setting", "wanPortIpv6Setting", "wanPortMacSetting"):
            if key not in row:
                missing += 1
                row_valid = False
        if not isinstance(row.get("portId"), str) or not row.get("portId"):
            invalid += 1
            row_valid = False
        ipv4 = row.get("wanPortIpv4Setting")
        if not isinstance(ipv4, Mapping):
            invalid += 1
            row_valid = False
        else:
            unknown += sum(k not in {"protoType", "vlanId", "qosTagEnable", "vlanPriority",
                                     "ipv4Static", "ipv4Dhcp", "ipv4Pppoe", "ipv4L2tp",
                                     "ipv4Pptp", "ipv4Dslite", "ipv4Mape", "ipv4Pppoa", "ipv4Ipoa"}
                           for k in ipv4)
            for key, typ in (("protoType", int), ("vlanId", int)):
                if key not in ipv4:
                    missing += 1
                    row_valid = False
                elif not isinstance(ipv4[key], typ) or (typ is int and isinstance(ipv4[key], bool)):
                    invalid += 1
                    row_valid = False
            if "qosTagEnable" in ipv4 and not isinstance(ipv4["qosTagEnable"], bool):
                invalid += 1
                row_valid = False
            code = ipv4.get("protoType")
            if isinstance(code, int) and not isinstance(code, bool):
                ipv4_protocols[code] += 1
        ipv6 = row.get("wanPortIpv6Setting")
        if not isinstance(ipv6, Mapping):
            invalid += 1
            row_valid = False
        elif not isinstance(ipv6.get("enable"), bool):
            if "enable" not in ipv6:
                missing += 1
            else:
                invalid += 1
            row_valid = False
        elif ipv6["enable"]:
            ipv6_enabled += 1
        else:
            ipv6_disabled += 1
        mac = row.get("wanPortMacSetting")
        if not isinstance(mac, Mapping):
            invalid += 1
            row_valid = False
        elif not isinstance(mac.get("method"), int) or isinstance(mac.get("method"), bool):
            if "method" not in mac:
                missing += 1
            else:
                invalid += 1
            row_valid = False
        dsl = row.get("dslSetting")
        if dsl is not None:
            if not isinstance(dsl, Mapping):
                invalid += 1
                row_valid = False
            else:
                unknown += sum(k not in {"portName", "portUuid", "portDesc", "location", "vpi", "vci",
                                         "encapMode", "merEnable", "merUsername", "merPassword",
                                         "isp", "modulationType"} for k in dsl)
                for key in ("isp", "location", "modulationType", "portUuid"):
                    if key not in dsl:
                        missing += 1
                        row_valid = False
                    elif ((key in {"portUuid", "location"} and
                           (not isinstance(dsl[key], str) or not dsl[key])) or
                          (key in {"isp", "modulationType"} and
                           (not isinstance(dsl[key], int) or isinstance(dsl[key], bool)))):
                        invalid += 1
                        row_valid = False
                if "merEnable" in dsl:
                    if isinstance(dsl["merEnable"], bool):
                        dsl_mer_enabled += int(dsl["merEnable"])
                        dsl_mer_disabled += int(not dsl["merEnable"])
                    else:
                        invalid += 1
                        row_valid = False
        valid_wan += int(row_valid)

    usb_rows = result.get("UsbPortsConfig")
    if "UsbPortsConfig" not in result:
        missing += 1
        usb_rows = []
    elif not isinstance(usb_rows, list) or len(usb_rows) > 64:
        invalid += 1
        usb_rows = []
    valid_usb = 0
    for row in usb_rows:
        if not isinstance(row, Mapping) or len(row) > 32:
            invalid += 1
            continue
        unknown += sum(key not in _USB for key in row)
        row_valid = True
        for key, typ in (("portId", str), ("authType", int), ("configType", int),
                         ("connectionMode", int), ("dnsEnable", bool), ("mtuSize", int)):
            if key not in row:
                missing += 1
                row_valid = False
            elif (not isinstance(row[key], typ) or (typ is int and isinstance(row[key], bool)) or
                  (typ is str and not row[key])):
                invalid += 1
                row_valid = False
        for key, counter in (("configType", usb_config_types), ("connectionMode", usb_connection_modes)):
            value = row.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                counter[value] += 1
        mtu = row.get("mtuSize")
        if isinstance(mtu, int) and not isinstance(mtu, bool) and not 576 <= mtu <= 1500:
            invalid += 1
            row_valid = False
        valid_usb += int(row_valid)

    return {
        "data": {
            "wan_port_count": len(wan_rows), "valid_wan_port_count": valid_wan,
            "ipv4_protocol_code_counts": _code_counts(ipv4_protocols),
            "ipv6_enabled_port_count": ipv6_enabled,
            "ipv6_disabled_port_count": ipv6_disabled,
            "dsl_mer_enabled_count": dsl_mer_enabled,
            "dsl_mer_disabled_count": dsl_mer_disabled,
            "usb_lte_port_count": len(usb_rows), "valid_usb_lte_port_count": valid_usb,
            "usb_config_type_code_counts": _code_counts(usb_config_types),
            "usb_connection_mode_code_counts": _code_counts(usb_connection_modes),
        },
        "missing_field_count": missing, "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
