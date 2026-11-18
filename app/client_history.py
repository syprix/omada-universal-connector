"""Privacy-preserving projection of paginated client-history rows."""
from __future__ import annotations

import re


class ClientHistoryError(ValueError):
    """Input or configured bounds cannot be handled safely."""

    def __init__(self, code: str = "client_history_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_ROWS = 4000
_MAX_FIELDS = 32
_MAX_KEY_LENGTH = 128
_MAX_SENSITIVE_STRING = 512
_MAX_IPV6_VALUES = 16
_MAX_AUTH_VALUES = 32
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAC_RE = re.compile(
    r"(?i)(?:(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|(?:[0-9a-f]{2}-){5}[0-9a-f]{2})\Z"
)

_INT64_FIELDS = frozenset({"download", "upload", "duration", "lastSeen", "associated"})
_INT32_FIELDS = frozenset({"port", "vid", "reasonType", "associationTime"})
_BOOL_FIELDS = frozenset({"guest"})
_SAFE_FIELDS = _INT64_FIELDS | _INT32_FIELDS | _BOOL_FIELDS
_PRIVATE_STRING_FIELDS = frozenset({"id", "name", "ssid", "reason", "deviceName", "ip"})
_PRIVATE_FIELDS = _PRIVATE_STRING_FIELDS | {"mac", "ipv6List", "authInfo"}
_KNOWN_FIELDS = _SAFE_FIELDS | _PRIVATE_FIELDS


def _mac_key(value: object) -> str | None:
    if not isinstance(value, str) or len(value) != 17 or not _MAC_RE.fullmatch(value):
        return None
    return value.replace(":", "").replace("-", "").lower()


def _bounded_string(value: object, maximum: int = _MAX_SENSITIVE_STRING) -> bool:
    return isinstance(value, str) and len(value) <= maximum


def project_client_history(rows: object, expected_client_mac: str) -> dict[str, object]:
    """Bind each row to the requested client and return safe raw scalar fields.

    ``rows`` must be the complete result of pagination. Oversized input fails
    closed instead of returning a truncated history. The documented private
    identity and free-text fields are used only for row binding/shape checks.
    """
    target_mac = _mac_key(expected_client_mac)
    if target_mac is None:
        raise ClientHistoryError()
    if not isinstance(rows, list):
        raise ClientHistoryError()
    if len(rows) > _MAX_ROWS:
        raise ClientHistoryError("client_history_response_too_large")

    projected_rows: list[dict[str, object]] = []
    missing_count = 0
    invalid_count = 0
    unknown_count = 0
    omitted_count = 0

    for row in rows:
        if not isinstance(row, dict):
            invalid_count += 1
            omitted_count += 1
            continue
        if len(row) > _MAX_FIELDS:
            raise ClientHistoryError("client_history_response_too_large")
        for key in row:
            if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
                raise ClientHistoryError("client_history_response_invalid")

        row_mac = _mac_key(row.get("mac"))
        if row_mac is None:
            missing_count += int("mac" not in row)
            invalid_count += int("mac" in row)
            omitted_count += 1
            continue
        if row_mac != target_mac:
            omitted_count += 1
            continue

        projected: dict[str, object] = {}
        for field in _SAFE_FIELDS:
            if field not in row:
                missing_count += 1
                continue
            value = row[field]
            if field in _INT64_FIELDS:
                valid = type(value) is int and _INT64_MIN <= value <= _INT64_MAX
            elif field in _INT32_FIELDS:
                valid = type(value) is int and _INT32_MIN <= value <= _INT32_MAX
            else:
                valid = type(value) is bool
            if valid:
                projected[field] = value
            else:
                invalid_count += 1

        for field in _PRIVATE_STRING_FIELDS:
            if field in row and not _bounded_string(row[field]):
                invalid_count += 1

        if "ipv6List" in row:
            ipv6_list = row["ipv6List"]
            if (not isinstance(ipv6_list, list) or len(ipv6_list) > _MAX_IPV6_VALUES or
                    any(not _bounded_string(item, 64) for item in ipv6_list)):
                invalid_count += 1

        if "authInfo" in row:
            auth_info = row["authInfo"]
            if not isinstance(auth_info, list) or len(auth_info) > _MAX_AUTH_VALUES:
                invalid_count += 1
            else:
                for auth in auth_info:
                    if not isinstance(auth, dict) or len(auth) > 4:
                        invalid_count += 1
                        continue
                    if set(auth) - {"authType", "info"}:
                        unknown_count += len(set(auth) - {"authType", "info"})
                    if ("authType" in auth and
                            not (type(auth["authType"]) is int and
                                 _INT32_MIN <= auth["authType"] <= _INT32_MAX)):
                        invalid_count += 1
                    if "info" in auth and not _bounded_string(auth["info"]):
                        invalid_count += 1
                    if "authType" not in auth or "info" not in auth:
                        missing_count += int("authType" not in auth) + int("info" not in auth)

        unknown_count += sum(1 for field in row if field not in _KNOWN_FIELDS)
        if not projected:
            omitted_count += 1
            continue
        projected_rows.append(projected)

    partial = bool(missing_count or invalid_count or unknown_count or omitted_count)
    return {
        "status": "ok",
        "resource": "client_history",
        "data": {"count": len(projected_rows), "rows": projected_rows},
        "partial": partial,
        "missing_field_count": missing_count,
        "invalid_field_count": invalid_count,
        "unknown_field_count": unknown_count,
        "omitted_count": omitted_count,
    }
