"""Combined redacted summary for the CBC template IPTV service GET."""
from __future__ import annotations

from typing import Any

try:
    from .site_igmp_summary import SiteIgmpSummaryError, summarize_site_template_igmp
    from .site_iptv_summary import SiteIptvSummaryError, summarize_site_iptv
except ImportError:  # direct execution in the image
    from site_igmp_summary import SiteIgmpSummaryError, summarize_site_template_igmp
    from site_iptv_summary import SiteIptvSummaryError, summarize_site_iptv


class SiteTemplateIptvServiceSummaryError(ValueError):
    """Raised when the combined IPTV service response cannot be projected."""


def summarize_site_template_iptv_service(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        raise SiteTemplateIptvServiceSummaryError("response_invalid")

    missing = invalid = unknown = 0
    unknown += len(set(result) - {"igmpSetting", "iptvSetting"})
    data: dict[str, object] = {"igmp": None, "iptv": None,
                              "iptv_settings_present": False}

    igmp_raw = result.get("igmpSetting")
    if isinstance(igmp_raw, dict):
        data["igmp_settings_present"] = True
        try:
            igmp = summarize_site_template_igmp(igmp_raw)
        except SiteIgmpSummaryError:
            raise SiteTemplateIptvServiceSummaryError("response_invalid") from None
        data["igmp"] = igmp["data"]
        missing += int(igmp["missing_field_count"])
        invalid += int(igmp["invalid_field_count"])
        unknown += int(igmp["unknown_field_count"])
    elif "igmpSetting" not in result:
        data["igmp_settings_present"] = False
        missing += 1
    else:
        data["igmp_settings_present"] = False
        invalid += 1

    iptv_raw = result.get("iptvSetting")
    if isinstance(iptv_raw, dict):
        data["iptv_settings_present"] = True
        try:
            iptv = summarize_site_iptv(iptv_raw)
        except SiteIptvSummaryError:
            raise SiteTemplateIptvServiceSummaryError("response_invalid") from None
        data["iptv"] = iptv["data"]
        missing += int(iptv["missing_field_count"])
        invalid += int(iptv["invalid_field_count"])
        unknown += int(iptv["unknown_field_count"])
        unknown += int(iptv["unknown_port_type_count"])
    elif "iptvSetting" in result:
        data["iptv_settings_present"] = False
        invalid += 1

    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
