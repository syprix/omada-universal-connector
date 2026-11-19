"""Summarize overlapping, explicitly observed client disconnection intervals."""
from __future__ import annotations

import itertools
import re


class ClientOutageOverlapError(ValueError):
    """Input cannot be represented as a bounded multi-client report."""


_REF = re.compile(r"[0-9a-f]{24}\Z")
_MAX_CLIENTS = 16


def _has_interval_overlap(left: list[tuple[int, int]],
                          right: list[tuple[int, int]]) -> bool:
    """Check sorted interval lists in linear time."""
    left_index = right_index = 0
    while left_index < len(left) and right_index < len(right):
        left_start, left_end = left[left_index]
        right_start, right_end = right[right_index]
        if max(left_start, right_start) < min(left_end, right_end):
            return True
        if left_end <= right_end:
            left_index += 1
        else:
            right_index += 1
    return False


def _timeline_events(value: object, expected_type: int) -> tuple[list[dict[str, object]], bool, int]:
    if not isinstance(value, dict) or value.get("status") != "ok":
        return [], True, 0
    data = value.get("data")
    sessions = data.get("sessions") if isinstance(data, dict) else None
    if not isinstance(sessions, list):
        return [], True, 0
    events: list[dict[str, object]] = []
    invalid = 0
    for session in sessions:
        rows = session.get("events") if isinstance(session, dict) else None
        if not isinstance(rows, list):
            invalid += 1
            continue
        for row in rows:
            if not isinstance(row, dict):
                invalid += 1
                continue
            event_type = row.get("event_type")
            timestamp = row.get("time_ms")
            if type(event_type) is not int or event_type != expected_type or type(timestamp) is not int:
                invalid += 1
                continue
            ap_ref = row.get("access_point_ref")
            if not isinstance(ap_ref, str) or not _REF.fullmatch(ap_ref):
                ap_ref = None
            events.append({"time_ms": timestamp, "event_type": event_type,
                           "access_point_ref": ap_ref})
    partial = (value.get("partial") is True or bool(value.get("missing_fields")) or
               type(value.get("omitted_field_count")) is int and value["omitted_field_count"] > 0 or
               invalid > 0)
    return events, partial, invalid


def project_client_outage_overlap(site_ref: str, start_ms: int, end_ms: int,
                                  client_results: list[dict[str, object]], *,
                                  ap_assignment_available: bool = True) -> dict[str, object]:
    """Count client-pair intervals that overlap on the same evidenced AP.

    Only type 1 (documented wireless disconnect) paired with a later type 0
    (documented wireless connect) forms a closed interval. An unmatched event
    or an absent AP mapping is retained as an explicit coverage gap.
    """
    if (not isinstance(site_ref, str) or not _REF.fullmatch(site_ref) or
            type(start_ms) is not int or type(end_ms) is not int or
            not 0 <= start_ms < end_ms or end_ms - start_ms > 86_400_000 or
            not isinstance(client_results, list) or
            not 2 <= len(client_results) <= _MAX_CLIENTS or
            type(ap_assignment_available) is not bool):
        raise ClientOutageOverlapError("client_outage_overlap_invalid")

    client_refs = [item.get("client_ref") if isinstance(item, dict) else None
                   for item in client_results]
    if (any(not isinstance(ref, str) or not _REF.fullmatch(ref) for ref in client_refs) or
            len(set(client_refs)) != len(client_refs)):
        raise ClientOutageOverlapError("client_refs_invalid")

    intervals: list[dict[str, object]] = []
    unknown_mapping_interval_count = 0
    unknown_mapping_event_count = 0
    open_disconnect_count = 0
    partial_clients = 0
    unavailable_clients = 0
    no_sample_clients = 0
    invalid_event_count = 0
    for item in client_results:
        client_ref = item["client_ref"]
        connect, connect_partial, connect_invalid = _timeline_events(item.get("connect"), 0)
        disconnect, disconnect_partial, disconnect_invalid = _timeline_events(
            item.get("disconnect"), 1)
        invalid_event_count += connect_invalid + disconnect_invalid
        source_unavailable = any(
            not isinstance(item.get(name), dict) or item[name].get("status") != "ok"
            for name in ("connect", "disconnect"))
        if source_unavailable:
            unavailable_clients += 1
        if connect_partial or disconnect_partial or source_unavailable:
            partial_clients += 1
        if not source_unavailable and not connect and not disconnect:
            no_sample_clients += 1

        unique: dict[tuple[int, int, str | None], dict[str, object]] = {}
        for event in connect + disconnect:
            unique[(event["time_ms"], event["event_type"], event["access_point_ref"])] = event
        ordered = sorted(unique.values(), key=lambda event: (event["time_ms"], event["event_type"]))
        pending: dict[str, object] | None = None
        for event in ordered:
            if event["event_type"] == 1:
                if event.get("access_point_ref") is None:
                    unknown_mapping_event_count += 1
                if pending is not None:
                    open_disconnect_count += 1
                pending = event
            elif event["event_type"] == 0 and pending is not None:
                finish = event["time_ms"]
                begin = pending["time_ms"]
                if type(begin) is int and type(finish) is int and finish > begin:
                    ap_ref = pending.get("access_point_ref")
                    if isinstance(ap_ref, str):
                        intervals.append({"client_ref": client_ref, "access_point_ref": ap_ref,
                                          "start_ms": begin, "end_ms": finish})
                    else:
                        unknown_mapping_interval_count += 1
                else:
                    invalid_event_count += 1
                pending = None
        if pending is not None:
            open_disconnect_count += 1

    by_ap: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for interval in intervals:
        by_ap.setdefault(interval["access_point_ref"], {}).setdefault(
            interval["client_ref"], []).append((interval["start_ms"], interval["end_ms"]))
    summaries = []
    for ap_ref, intervals_by_client in sorted(by_ap.items()):
        pairs: set[tuple[str, str]] = set()
        sorted_by_client = {ref: sorted(rows)
                            for ref, rows in intervals_by_client.items()}
        for client_left, client_right in itertools.combinations(
                sorted(sorted_by_client), 2):
            left = sorted_by_client[client_left]
            right = sorted_by_client[client_right]
            if _has_interval_overlap(left, right):
                pairs.add((client_left, client_right))
        affected = {ref for pair in pairs for ref in pair}
        if pairs:
            summaries.append({"access_point_ref": ap_ref,
                              "confirmed_overlapping_client_pair_count": len(pairs),
                              "affected_client_count": len(affected)})

    partial = bool(partial_clients or unavailable_clients or no_sample_clients or
                   unknown_mapping_interval_count or unknown_mapping_event_count or
                   open_disconnect_count or invalid_event_count or not ap_assignment_available)
    gaps = []
    for condition, label in ((partial_clients, "partial_client_source"),
                             (unavailable_clients, "unavailable_client_source"),
                             (no_sample_clients, "client_without_samples"),
                             (unknown_mapping_interval_count or unknown_mapping_event_count,
                              "unknown_access_point_mapping"),
                             (not ap_assignment_available, "ap_inventory_unavailable"),
                             (open_disconnect_count, "unclosed_disconnect_interval"),
                             (invalid_event_count, "invalid_or_unexpected_event")):
        if condition:
            gaps.append(label)
    return {
        "status": "ok", "resource": "client_outage_overlap_summary",
        "site_ref": site_ref, "window_start_ms": start_ms, "window_end_ms": end_ms,
        "selected_client_count": len(client_results),
        "confirmed_overlaps_by_access_point": summaries,
        "unknown_access_point_mapping_interval_count": unknown_mapping_interval_count,
        "unknown_access_point_mapping_event_count": unknown_mapping_event_count,
        "unclosed_disconnect_interval_count": open_disconnect_count,
        "ap_assignment_available": ap_assignment_available,
        "source_coverage": {"partial_client_count": partial_clients,
                            "unavailable_client_timeline_count": unavailable_clients,
                            "client_without_samples_count": no_sample_clients,
                            "invalid_or_unexpected_event_count": invalid_event_count},
        "connection_cause": "not_inferred", "partial": partial,
        "gap_indicators": gaps,
    }
