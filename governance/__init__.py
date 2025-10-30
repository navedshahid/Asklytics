"""Governance utilities (masking, RBAC, governance APIs).

This package centralises the ISO-27001-inspired controls described in
agent.md: masking, role-based access, and governance/audit endpoints.
"""

from .masker import MaskingPolicy, mask_row, mask_rows
from .rbac import PII_VIEWER_ROLES, can_view_pii, resolve_roles
from .routes import governance_bp, set_audit_root

__all__ = [
    "MaskingPolicy",
    "mask_row",
    "mask_rows",
    "PII_VIEWER_ROLES",
    "can_view_pii",
    "resolve_roles",
    "governance_bp",
    "set_audit_root",
]
