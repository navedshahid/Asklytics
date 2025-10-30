"""Tiny RBAC helpers used to guard masking/unmasking decisions."""

from __future__ import annotations

from typing import Iterable, Set

from flask import Request

# Roles that are permitted to view unmasked PII by default.
PII_VIEWER_ROLES: Set[str] = {"pii_viewer", "auditor", "admin", "security"}


def _split_roles(raw: str | None) -> Set[str]:
    if not raw:
        return set()
    parts = [r.strip().lower() for r in raw.replace(";", ",").split(",")]
    return {p for p in parts if p}


def resolve_roles(request: Request) -> Set[str]:
    """Resolve roles from headers/cookies/query params.

    The project primarily uses ``X-Role`` but we support ``X-Roles`` (CSV) and
    a ``role`` cookie for completeness.
    """

    roles: Set[str] = set()
    roles |= _split_roles(request.headers.get("X-Role"))
    roles |= _split_roles(request.headers.get("X-Roles"))
    try:
        roles |= _split_roles(request.cookies.get("role"))
    except Exception:
        pass
    # Optional query param override (useful for automated tests)
    roles |= _split_roles(request.args.get("role"))
    return roles


def can_view_pii(roles: Iterable[str]) -> bool:
    return any(r in PII_VIEWER_ROLES for r in roles)
