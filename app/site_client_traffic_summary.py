"""Page-level aggregate traffic summaries without client or app identities."""
from __future__ import annotations

from typing import Any


class SiteClientTrafficSummaryError(ValueError):
    """Raised when the paginated client traffic response exceeds its bounds."""


_PAGE_FIELDS = {"totalRows", "currentPage", "currentSize", "data", "clientTrafficFilters"}
_CLIENT_FIELDS = {
    "type", "manager", "clientName", "mac", "traffic", "trafficPercent", "upload",
    "uploadTrafficPercent", "download", "downloadTrafficPercent", "totalApplications",
    "applicationList", "network", "vlanId",
}
_APPLICATION_FIELDS = {
    "applicationName", "applicationId", "applicationDescription", "familyId", "familyName",
    "traffic", "trafficPercent", "clientsCount",
}
_FILTER_FIELDS = {"network", "vlanId"}
_MAX_PAGE_SIZE = 100
_MAX_PAGE_NUMBER = 10_000
_MAX_APPLICATIONS_PER_CLIENT = 200
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1


def project_site_client_traffic_summary(
        result: Any, page_number: int, page_size: int) -> dict[str, object]:
    if (type(page_number) is not int or not 0 <= page_number <= _MAX_PAGE_NUMBER or
            type(page_size) is not int or not 1 <= page_size <= _MAX_PAGE_SIZE):
        raise SiteClientTrafficSummaryError("request_invalid")
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteClientTrafficSummaryError("response_invalid")
    rows = result.get("data")
    if not isinstance(rows, list) or len(rows) > page_size:
        raise SiteClientTrafficSummaryError("response_invalid")

    missing = invalid = 0
    unknown = len(set(result) - _PAGE_FIELDS)
    metadata: dict[str, int] = {}
    for key, upper in (("totalRows", _INT64_MAX),
                       ("currentPage", _INT32_MAX), ("currentSize", _INT32_MAX)):
        value = result.get(key)
        if key not in result:
            missing += 1
        elif type(value) is not int or not 0 <= value <= upper:
            invalid += 1
        else:
            metadata[key] = value

    if "totalRows" in metadata and metadata["totalRows"] > page_number * page_size and not rows:
        invalid += 1
    if ("totalRows" in metadata and
            metadata["totalRows"] < page_number * page_size + len(rows)):
        invalid += 1
    # The connector is zero-based, while Omada's documented query page starts at 1.
    if "currentPage" in metadata and metadata["currentPage"] != page_number + 1:
        invalid += 1
    if "currentSize" in metadata and metadata["currentSize"] > page_size:
        invalid += 1

    totals = {key: 0 for key in ("traffic", "upload", "download", "totalApplications")}
    peaks = {key: 0 for key in ("traffic", "upload", "download")}
    application_traffic_total = application_detail_count = 0
    application_traffic_complete = True
    valid_clients = 0
    client_complete = {key: True for key in totals}
    for row in rows:
        if not isinstance(row, dict) or len(row) > 20:
            invalid += 1
            for key in client_complete:
                client_complete[key] = False
            continue
        unknown += len(set(row) - _CLIENT_FIELDS)
        valid_clients += 1
        for key, upper in (("traffic", _INT64_MAX), ("upload", _INT64_MAX),
                           ("download", _INT64_MAX), ("totalApplications", _INT32_MAX)):
            if key not in row:
                missing += 1
                client_complete[key] = False
                continue
            value = row[key]
            if type(value) is not int or not 0 <= value <= upper:
                invalid += 1
                client_complete[key] = False
                continue
            if totals[key] > _INT64_MAX - value:
                invalid += 1
                client_complete[key] = False
                continue
            totals[key] += value
            if key in peaks:
                peaks[key] = max(peaks[key], value)

        if "applicationList" in row:
            applications = row["applicationList"]
            if (not isinstance(applications, list) or
                    len(applications) > _MAX_APPLICATIONS_PER_CLIENT):
                invalid += 1
                application_traffic_complete = False
            else:
                for application in applications:
                    if not isinstance(application, dict) or len(application) > 12:
                        invalid += 1
                        application_traffic_complete = False
                        continue
                    unknown += len(set(application) - _APPLICATION_FIELDS)
                    application_detail_count += 1
                    value = application.get("traffic")
                    if type(value) is int and 0 <= value <= _INT64_MAX:
                        if application_traffic_total > _INT64_MAX - value:
                            invalid += 1
                            application_traffic_complete = False
                        else:
                            application_traffic_total += value
                    elif "traffic" in application:
                        invalid += 1
                        application_traffic_complete = False
                    else:
                        missing += 1
                        application_traffic_complete = False

    if "clientTrafficFilters" in result:
        filters = result["clientTrafficFilters"]
        if not isinstance(filters, list) or len(filters) > 256:
            invalid += 1
        else:
            for item in filters:
                if not isinstance(item, dict) or len(item) > 4:
                    invalid += 1
                    continue
                unknown += len(set(item) - _FILTER_FIELDS)
                if any(key in item and not isinstance(item[key], str) for key in _FILTER_FIELDS):
                    invalid += 1

    total_rows = metadata.get("totalRows")
    has_more = (total_rows is None or
                page_number * page_size + len(rows) < total_rows)
    data: dict[str, object] = {
        "page_number": page_number,
        "page_size": page_size,
        "total_rows": total_rows,
        "returned_client_count": valid_clients,
        "has_more_pages": has_more,
        "client_traffic_total": totals["traffic"] if client_complete["traffic"] else None,
        "client_traffic_peak_per_client": peaks["traffic"] if client_complete["traffic"] else None,
        "upload_traffic_total": totals["upload"] if client_complete["upload"] else None,
        "download_traffic_total": totals["download"] if client_complete["download"] else None,
        "application_count_total": totals["totalApplications"] if client_complete["totalApplications"] else None,
        "application_detail_row_count": application_detail_count,
        "application_detail_traffic_total": (
            application_traffic_total if application_traffic_complete else None),
    }
    partial = bool(missing or invalid or unknown or has_more or
                   not all(client_complete.values()) or valid_clients != len(rows))
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": partial}
