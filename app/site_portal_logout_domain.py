"""Projection for the documented portal logout domain read."""

from __future__ import annotations

from collections.abc import Mapping


class SitePortalLogoutDomainError(ValueError):
    """The controller response does not match the documented shape."""


def project_site_portal_logout_domain(result: object) -> dict[str, str]:
    """Return the documented domain string, including the documented empty value."""
    if not isinstance(result, Mapping):
        raise SitePortalLogoutDomainError("result must be an object")
    domain = result.get("domain")
    if not isinstance(domain, str):
        raise SitePortalLogoutDomainError("domain must be a string")
    return {"domain": domain}
