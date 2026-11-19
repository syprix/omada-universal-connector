"""Summarize reciprocal AP roaming sequences and intervening disconnects."""
from __future__ import annotations

import re
from collections import defaultdict


class ClientRoamingBacktrackError(ValueError):
    """Input cannot be represented as a bounded roaming report."""


_REF = re.compile(r"[0-9a-f]{24}\Z")
_MAX_CLIENTS = 16


def _timeline_rows(value: object, expected_type: int, start_ms: int, end_ms
                   ) -> tuple[list[dict[str, object]], bool, bool, int, int]:
    """Return usable rows, source-unavailable, event-gap, invalid, unknown-map."""
    if not isinstance(value, dict) or value.get("status") != "ok":
        return [], True, True, 0, 0
    data = value.get("data")
    sessions = data.get("sessions") if isinstance(data, dict) else None
    if not isinstance(sessions, list):
        return [], False, True, 0, 0

    rows: list[dict[str, object]] = []
    invalid = 0
    unknown_mapping = 0
    event_gap = bool(value.get("missing_fields"))
    omitted = value.get("omitted_fields")
    if isinstance(omitted, list) and any(
            item != "ap_assignment_unavailable" and
            (item == "invalid_events" or item == "invalid_sessions" or
             "events" in str(item) or "eventType" in str(item) or ".time" in str(item))
            for item in omitted):
        event_gap = True

    for session in sessions:
        events = session.get("events") if isinstance(session, dict) else None
        if not isinstance(events, list):
            invalid += 1
            event_gap = True
            continue
        for event in events:
            if not isinstance(event, dict) or event.get("event_type") != expected_type:
                invalid += 1
                event_gap = True
                continue
            timestamp = event.get("time_ms")
            if type(timestamp) is not int or not start_ms <= timestamp <= end_ms:
                invalid += 1
                event_gap = True
                continue
            row: dict[str, object] = {"time_ms": timestamp}
            if expected_type == 2:
                previous = event.get("previous_access_point_ref")
                current = event.get("access_point_ref")
                if (not isinstance(previous, str) or not _REF.fullmatch(previous) or
                        not isinstance(current, str) or not _REF.fullmatch(current) or
                        previous == current):
                    unknown_mapping += 1
                    event_gap = True
                    continue
                row["previous_access_point_ref"] = previous
                row["access_point_ref"] = current
            rows.append(row)
    rows.sort(key=lambda item: item["time_ms"])
    return rows, False, event_gap, invalid, unknown_mapping


def project_client_roaming_backtrack(
    site_ref: str, start_ms: int, end_ms: int,
    client_timelines: list[dict[str, object]], *,
    ap_inventory_available: bool = True,
) -> dict[str, object]:
    """Count A→B→A roaming and keep intervening disconnects/gaps distinct."""
    if (not isinstance(site_ref, str) or not _REF.fullmatch(site_ref) or
            type(start_ms) is not int or type(end_ms) is not int or
            not 0 <= start_ms < end_ms or end_ms - start_ms > 86_400_000 or
            not isinstance(client_timelines, list) or
            not 1 <= len(client_timelines) <= _MAX_CLIENTS or
            type(ap_inventory_available) is not bool):
        raise ClientRoamingBacktrackError("client_roaming_backtrack_invalid")
    client_refs = [item.get("client_ref") if isinstance(item, dict) else None
                   for item in client_timelines]
    if (any(not isinstance(ref, str) or not _REF.fullmatch(ref) for ref in client_refs) or
            len(set(client_refs)) != len(client_refs)):
        raise ClientRoamingBacktrackError("client_refs_invalid")

    pair_clients: dict[tuple[str, str], set[str]] = defaultdict(set)
    pair_sequence_counts: dict[tuple[str, str], int] = defaultdict(int)
    pair_events: dict[tuple[str, str], set[tuple[int, str, str]]] = defaultdict(set)
    partial_clients = unavailable_clients = no_sample_clients = 0
    invalid_event_count = unknown_mapping_event_count = 0
    separated_transition_count = reconnect_after_disconnect_count = 0
    disconnect_without_reconnect_count = event_gap_pair_count = 0
    gap_clients = 0

    for item in client_timelines:
        # ``timeline`` remains a fixture compatibility alias for older unit callers.
        roaming_value = item.get("roaming", item.get("timeline"))
        disconnect_value = item.get("disconnect")
        connect_value = item.get("connect")
        roaming, roam_unavailable, roam_gap, invalid, unknown = _timeline_rows(
            roaming_value, 2, start_ms, end_ms)
        disconnects, disconnect_unavailable, disconnect_gap, bad_disconnects, _ = _timeline_rows(
            disconnect_value, 1, start_ms, end_ms)
        connects, connect_unavailable, connect_gap, bad_connects, _ = _timeline_rows(
            connect_value, 0, start_ms, end_ms)
        invalid_event_count += invalid + bad_disconnects + bad_connects
        unknown_mapping_event_count += unknown
        sources = (roaming_value, disconnect_value, connect_value)
        unavailable = any(not isinstance(source, dict) or source.get("status") != "ok"
                          for source in sources)
        if unavailable:
            unavailable_clients += 1
        partial = any(isinstance(source, dict) and
                      (source.get("partial") is True or bool(source.get("missing_fields")) or
                       type(source.get("omitted_field_count")) is int and
                       source["omitted_field_count"] > 0)
                      for source in sources)
        if partial or invalid or unknown or roam_gap or disconnect_gap or connect_gap:
            partial_clients += 1
        # Type-0 connect data refines a confirmed type-1 separation; it does
        # not block a return-roam count when the complete disconnect source
        # shows no intervening separation.
        source_gap = (roam_gap or disconnect_gap or roam_unavailable or
                      disconnect_unavailable)
        if source_gap:
            gap_clients += 1
        if not roaming and not invalid and not unknown and not unavailable:
            no_sample_clients += 1

        client_ref = item["client_ref"]
        for left, right in zip(roaming, roaming[1:]):
            if right["time_ms"] <= left["time_ms"]:
                invalid_event_count += 1
                continue
            if (left["previous_access_point_ref"] != right["access_point_ref"] or
                    left["access_point_ref"] != right["previous_access_point_ref"]):
                continue
            if source_gap or unknown or invalid:
                event_gap_pair_count += 1
                continue
            between_disconnects = [event["time_ms"] for event in disconnects
                                   if left["time_ms"] < event["time_ms"] < right["time_ms"]]
            if between_disconnects:
                separated_transition_count += 1
                latest_disconnect = max(between_disconnects)
                if any(latest_disconnect < event["time_ms"] < right["time_ms"]
                       for event in connects):
                    reconnect_after_disconnect_count += 1
                elif not connect_gap:
                    disconnect_without_reconnect_count += 1
                continue

            pair = tuple(sorted((left["previous_access_point_ref"],
                                 left["access_point_ref"])))
            pair_sequence_counts[pair] += 1
            pair_clients[pair].add(client_ref)
            pair_events[pair].update((
                (left["time_ms"], left["previous_access_point_ref"],
                 left["access_point_ref"]),
                (right["time_ms"], right["previous_access_point_ref"],
                 right["access_point_ref"]),
            ))

    summaries = []
    for pair in sorted(pair_sequence_counts):
        summaries.append({
            "access_point_pair": list(pair),
            "back_and_forth_sequence_count": pair_sequence_counts[pair],
            "affected_client_count": len(pair_clients[pair]),
            "involved_roaming_event_count": len(pair_events[pair]),
        })
    partial = bool(partial_clients or unavailable_clients or no_sample_clients or
                   invalid_event_count or unknown_mapping_event_count or
                   not ap_inventory_available or
                   event_gap_pair_count)
    gaps = []
    for condition, label in (
        (partial_clients, "partial_client_source"),
        (unavailable_clients, "unavailable_client_timeline"),
        (no_sample_clients, "client_without_roaming_samples"),
        (gap_clients, "client_event_gap"),
        (unknown_mapping_event_count, "unknown_access_point_mapping"),
        (not ap_inventory_available, "ap_inventory_unavailable"),
        (invalid_event_count, "invalid_or_out_of_window_event"),
        (event_gap_pair_count, "reciprocal_sequence_crosses_event_gap"),
    ):
        if condition:
            gaps.append(label)
    return {
        "status": "ok", "resource": "client_roaming_backtrack_summary",
        "site_ref": site_ref, "window_start_ms": start_ms,
        "window_end_ms": end_ms, "selected_client_count": len(client_timelines),
        "back_and_forth_by_access_point_pair": summaries,
        "separated_roaming_transition_count": separated_transition_count,
        "reconnected_after_separation_count": reconnect_after_disconnect_count,
        "separation_without_observed_reconnect_count": disconnect_without_reconnect_count,
        "reciprocal_sequence_event_gap_count": event_gap_pair_count,
        "source_coverage": {
            "partial_client_count": partial_clients,
            "unavailable_client_timeline_count": unavailable_clients,
            "clients_without_roaming_samples_count": no_sample_clients,
            "event_gap_client_count": gap_clients,
            "unknown_access_point_mapping_event_count": unknown_mapping_event_count,
            "invalid_or_out_of_window_event_count": invalid_event_count,
        },
        "ap_inventory_available": ap_inventory_available,
        "connection_cause": "not_inferred", "partial": partial,
        "gap_indicators": gaps,
    }
