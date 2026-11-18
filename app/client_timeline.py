"""Privacy-preserving projection of documented client connection events."""
from __future__ import annotations

import re


class ClientTimelineError(ValueError):
    """Input or configured bounds cannot be handled safely."""

    def __init__(self, code: str = "client_timeline_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 32
_MAX_SESSIONS = 128
_MAX_EVENTS = 1024
_INT64_MAX = 2**63 - 1
_EVENT_TYPES = frozenset({0, 1, 2, 3, 100, 101, 102, 200, 201, 202})
_SESSION_PRIVATE_FIELDS = frozenset({"mac"})
_EVENT_PRIVATE_FIELDS = frozenset({"content", "attributes"})
_MAC_RE = re.compile(
    r"(?i)(?:(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|(?:[0-9a-f]{2}-){5}[0-9a-f]{2})\Z"
)


def _mac_key(value: object) -> str | None:
    if not isinstance(value, str) or not _MAC_RE.fullmatch(value):
        return None
    return value.replace(":", "").replace("-", "").lower()


def project_client_timeline(raw: object, start_ms: int, end_ms: int,
                            expected_client_mac: str) -> dict[str, object]:
    """Project bounded session/event timestamps and documented numeric codes.

    Known private fields (session MAC, event content and attributes) are
    discarded without echo. Sessions without a valid matching MAC are omitted
    because they cannot safely be attributed to the selected client. Unknown
    fields, missing values, null times and invalid/out-of-window values are
    represented only by partial metadata; sensitive values are never echoed.
    """
    if (type(start_ms) is not int or type(end_ms) is not int or
            not 0 <= start_ms <= end_ms <= _INT64_MAX):
        raise ClientTimelineError()
    expected_mac_key = _mac_key(expected_client_mac)
    if expected_mac_key is None:
        raise ClientTimelineError()
    if raw is not None and not isinstance(raw, list):
        raise ClientTimelineError()
    if isinstance(raw, list) and len(raw) > _MAX_SESSIONS:
        raise ClientTimelineError()

    sessions: list[dict[str, object]] = []
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0
    total_events = 0

    if raw is None:
        missing.append("sessions")
        omitted_count += 1
    else:
        for session_index, source in enumerate(raw):
            if not isinstance(source, dict):
                omitted.add("invalid_sessions")
                omitted_count += 1
                continue
            if len(source) > _MAX_FIELDS:
                raise ClientTimelineError()

            event_value = source.get("events")
            if isinstance(event_value, list):
                total_events += len(event_value)
                if total_events > _MAX_EVENTS:
                    raise ClientTimelineError()
                # Enforce nested-object bounds even for sessions that will be
                # discarded below due to missing or mismatched identity.
                if any(isinstance(event, dict) and len(event) > _MAX_FIELDS
                       for event in event_value):
                    raise ClientTimelineError()

            session_mac_key = _mac_key(source.get("mac")) if "mac" in source else None
            if "mac" not in source:
                missing.append(f"sessions[{session_index}].mac")
                omitted_count += 1
                omitted.add("session_identity_unverified")
                continue
            elif session_mac_key is None or session_mac_key != expected_mac_key:
                omitted.add("session_identity_mismatch")
                omitted_count += 1
                continue

            session: dict[str, object] = {}
            session_values: dict[str, int | None] = {}
            for field in ("start", "end"):
                path = f"sessions[{session_index}].{field}"
                if field not in source:
                    missing.append(path)
                    omitted_count += 1
                    continue
                value = source[field]
                if value is None:
                    session_values[field] = None
                    session["start_ms" if field == "start" else "end_ms"] = None
                    omitted.add(path)
                    omitted_count += 1
                elif type(value) is int and 0 <= value <= _INT64_MAX and start_ms <= value <= end_ms:
                    session_values[field] = value
                    session["start_ms" if field == "start" else "end_ms"] = value
                else:
                    omitted.add(path)
                    omitted_count += 1

            if (type(session_values.get("start")) is int and
                    type(session_values.get("end")) is int and
                    session_values["start"] > session_values["end"]):
                session.pop("end_ms", None)
                omitted.add(f"sessions[{session_index}].end")
                omitted_count += 1

            if "events" not in source:
                missing.append(f"sessions[{session_index}].events")
                omitted_count += 1
            elif not isinstance(event_value, list):
                omitted.add(f"sessions[{session_index}].events")
                omitted_count += 1
            else:
                projected_events: list[dict[str, object]] = []
                for event_index, event in enumerate(event_value):
                    if not isinstance(event, dict):
                        omitted.add("invalid_events")
                        omitted_count += 1
                        continue
                    if len(event) > _MAX_FIELDS:
                        raise ClientTimelineError()
                    projected_event: dict[str, object] = {}
                    for field in ("time", "eventType"):
                        path = f"sessions[{session_index}].events[{event_index}].{field}"
                        if field not in event:
                            missing.append(path)
                            omitted_count += 1
                            continue
                        value = event[field]
                        if field == "time":
                            if value is None:
                                projected_event["time_ms"] = None
                                omitted.add(path)
                                omitted_count += 1
                            elif (type(value) is int and 0 <= value <= _INT64_MAX and
                                  start_ms <= value <= end_ms):
                                projected_event["time_ms"] = value
                            else:
                                omitted.add(path)
                                omitted_count += 1
                        elif type(value) is int and value in _EVENT_TYPES:
                            projected_event["event_type"] = value
                        else:
                            omitted.add(path)
                            omitted_count += 1

                    unknown = sum(1 for key in event
                                  if key not in {"time", "eventType"} | _EVENT_PRIVATE_FIELDS)
                    if unknown:
                        omitted.add("unknown_fields")
                        omitted_count += unknown
                    projected_events.append(projected_event)
                session["events"] = projected_events

            unknown = sum(1 for key in source
                          if key not in {"start", "end", "events"} | _SESSION_PRIVATE_FIELDS)
            if unknown:
                omitted.add("unknown_fields")
                omitted_count += unknown
            sessions.append(session)

    return {
        "status": "ok",
        "resource": "client_timeline",
        "data": {"sessions": sessions} if raw is not None else {},
        "partial": bool(missing or omitted_count),
        "missing_fields": missing,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
    }
