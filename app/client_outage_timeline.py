"""Compose privacy-safe client and site context for a bounded outage window."""
from __future__ import annotations

import re


class ClientOutageTimelineError(ValueError):
    pass


_EVENT_KINDS = ("connect", "association", "roaming", "disconnect")


def _age(timestamp: int | None, now_ms: int) -> int | None:
    return None if timestamp is None else max(0, now_ms - timestamp)


def _gap_indicators(*, partial: bool, missing: int, omitted: int,
                    sample_count: int) -> list[str]:
    indicators = []
    if sample_count == 0:
        indicators.append("no_samples")
    if partial:
        indicators.append("partial_source")
    if missing:
        indicators.append("missing_fields")
    if omitted:
        indicators.append("omitted_or_invalid_fields")
    return indicators


def project_client_outage_timeline(client_ref: str, start_ms: int, end_ms: int,
                                   client_timeline_results: dict[str, object],
                                   health_result: object, event_result: object,
                                   alert_result: object, now_ms: int
                                   ) -> dict[str, object]:
    """Join only validated millisecond points and bounded aggregate site context.

    Site log timestamp units are not named in the source schema. Their counts and
    pagination coverage are retained, but no age or client-level correlation is
    inferred from their response timestamps.
    """
    if (not isinstance(client_ref, str) or not re.fullmatch(r"[0-9a-f]{24}", client_ref) or
            type(start_ms) is not int or type(end_ms) is not int or
            type(now_ms) is not int or not 0 <= start_ms <= end_ms <= now_ms + 60_000 or
            end_ms - start_ms > 86_400_000 or not isinstance(client_timeline_results, dict)):
        raise ClientOutageTimelineError("client_outage_timeline_invalid")

    events: list[dict[str, int]] = []
    event_missing = event_omitted = 0
    event_partial = False
    event_sources = {}
    for kind in _EVENT_KINDS:
        value = client_timeline_results.get(kind)
        if not isinstance(value, dict) or value.get("status") != "ok":
            code = value.get("error") if isinstance(value, dict) else None
            event_sources[kind] = {"status": "unavailable",
                                   "error": code if isinstance(code, str) else "source_unavailable",
                                   "sample_count": 0, "partial": True,
                                   "gap_indicators": ["source_unavailable"]}
            event_partial = True
            continue
        data = value.get("data")
        sessions = data.get("sessions") if isinstance(data, dict) else None
        samples: list[dict[str, int]] = []
        if isinstance(sessions, list):
            for session in sessions:
                if not isinstance(session, dict) or not isinstance(session.get("events"), list):
                    continue
                for item in session["events"]:
                    if (isinstance(item, dict) and type(item.get("time_ms")) is int and
                            type(item.get("event_type")) is int):
                        sample = {"time_ms": item["time_ms"], "event_type": item["event_type"]}
                        samples.append(sample)
        samples.sort(key=lambda item: (item["time_ms"], item["event_type"]))
        missing = value.get("missing_fields")
        omitted = value.get("omitted_field_count")
        missing_count = len(missing) if isinstance(missing, list) else 0
        omitted_count = omitted if type(omitted) is int and omitted >= 0 else 0
        partial = value.get("partial") is True
        latest = max((item["time_ms"] for item in samples), default=None)
        event_sources[kind] = {
            "status": "ok", "sample_count": len(samples),
            "latest_timestamp_ms": latest, "data_age_ms": _age(latest, now_ms),
            "partial": partial, "missing_field_count": missing_count,
            "omitted_field_count": omitted_count,
            "gap_indicators": _gap_indicators(partial=partial, missing=missing_count,
                                               omitted=omitted_count,
                                               sample_count=len(samples)),
        }
        event_partial |= partial
        event_missing += missing_count
        event_omitted += omitted_count
        events.extend(samples)

    # The four upstream type filters can overlap. Preserve one copy of each
    # documented timestamp/type pair without retaining session or AP identity.
    events = sorted({(item["time_ms"], item["event_type"]) for item in events})
    projected_events = [{"time_ms": time_ms, "event_type": event_type}
                        for time_ms, event_type in events]
    roaming = [item for item in projected_events if item["event_type"] == 2]

    if not isinstance(health_result, dict) or health_result.get("status") != "ok":
        health_source: dict[str, object] = {"status": "unavailable", "sample_count": 0,
                                            "error": (health_result.get("error")
                                                      if isinstance(health_result, dict) else
                                                      "source_unavailable"),
                                            "partial": True,
                                            "gap_indicators": ["source_unavailable"]}
        health_points: list[dict[str, int]] = []
    else:
        health_data = health_result.get("data")
        raw_scores = health_data.get("scores") if isinstance(health_data, dict) else None
        health_points = ([{"time_ms": point["time_ms"], "score": point["score"]}
                         for point in raw_scores if isinstance(point, dict) and
                         type(point.get("time_ms")) is int and type(point.get("score")) is int]
                         if isinstance(raw_scores, list) else [])
        health_points.sort(key=lambda item: item["time_ms"])
        missing = health_result.get("missing_fields")
        omitted = health_result.get("omitted_field_count")
        missing_count = len(missing) if isinstance(missing, list) else 0
        omitted_count = omitted if type(omitted) is int and omitted >= 0 else 0
        partial = health_result.get("partial") is True
        latest = max((item["time_ms"] for item in health_points), default=None)
        health_source = {
            "status": "ok", "sample_count": len(health_points),
            "latest_timestamp_ms": latest, "data_age_ms": _age(latest, now_ms),
            "partial": partial, "missing_field_count": missing_count,
            "omitted_field_count": omitted_count,
            "gap_indicators": _gap_indicators(partial=partial, missing=missing_count,
                                               omitted=omitted_count,
                                               sample_count=len(health_points)),
        }

    def site_source(value: object) -> dict[str, object]:
        if not isinstance(value, dict) or value.get("status") != "ok":
            code = value.get("error") if isinstance(value, dict) else None
            return {"status": "unavailable", "error": code if isinstance(code, str)
                    else "source_unavailable", "partial": True,
                    "gap_indicators": ["source_unavailable"],
                    "timestamp_age_ms": None,
                    "timestamp_age_reason": "source schema does not name the timestamp unit"}
        output = {key: value[key] for key in
                  ("returned_count", "total_count", "partial", "module_counts",
                   "severity_counts", "pagination") if key in value}
        output["status"] = "ok"
        indicators = []
        if value.get("partial") is True:
            indicators.append("partial_source")
        if value.get("returned_count") == 0:
            indicators.append("no_samples")
        output["gap_indicators"] = indicators
        output["timestamp_age_ms"] = None
        output["timestamp_age_reason"] = "source schema does not name the timestamp unit"
        return output

    sites = {"events": site_source(event_result), "alerts": site_source(alert_result)}
    all_partial = (event_partial or health_source.get("partial") is True or
                   any(item.get("partial") is True for item in sites.values()))
    return {
        "status": "ok", "resource": "client_outage_timeline",
        "client_ref": client_ref, "window_start_ms": start_ms, "window_end_ms": end_ms,
        "client_events": projected_events, "roaming_events": roaming,
        "health_scores": health_points,
        "sources": {"client_events": event_sources, "health_scores": health_source,
                    "site_event_context": sites},
        "site_wide_event_context_only": True,
        "connection_cause": "not_inferred",
        "partial": all_partial,
        "gap_indicators": _gap_indicators(
            partial=all_partial, missing=event_missing, omitted=event_omitted,
            sample_count=len(projected_events) + len(health_points)),
    }
