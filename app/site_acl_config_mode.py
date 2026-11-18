"""Projection for the site ACL mode read."""

from __future__ import annotations

from collections.abc import Mapping


class SiteAclConfigModeError(ValueError):
    """The controller response does not match the documented schema."""


def project_site_acl_config_mode(result: object) -> dict[str, object]:
    if not isinstance(result, Mapping) or len(result) > 8:
        raise SiteAclConfigModeError("result must be a bounded object")
    missing = int("mode" not in result)
    invalid = 0
    mode = result.get("mode")
    if "mode" in result and (
            not isinstance(mode, int) or isinstance(mode, bool) or
            not -(2**31) <= mode < 2**31 or mode not in (0, 1)):
        invalid = 1
        mode = None
    unknown = sum(key != "mode" for key in result)
    names = {0: "through_profiles", 1: "custom"}
    return {
        "data": {
            "mode_code": mode,
            "mode_name": names.get(mode) if mode is not None else None,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid),
    }
