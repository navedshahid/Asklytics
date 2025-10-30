"""Row masking utilities used across the AskLytics stack.

The goal is to provide a lightweight, dependency-free helper that obeys the
ISO-27001-aligned defaults described in agent.md:

* Mask PII by default for every user.
* Allow explicit unmasking only for authorised roles.
* Prefer metadata-driven masking (mm_column.IsPII) but fall back to heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, Set

_SENSITIVE_KEYWORDS: Set[str] = {
    "name",
    "first_name",
    "last_name",
    "fullname",
    "email",
    "phone",
    "mobile",
    "ssn",
    "tax",
    "passport",
    "dob",
    "birth",
    "address",
    "street",
    "city",
    "zip",
    "postal",
    "iban",
    "account",
    "card",
}


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


@dataclass
class MaskingPolicy:
    """Simple masking policy with metadata-aware overrides."""

    pii_columns: Mapping[str, Iterable[str]] | None = None
    mask_token: str = "***"
    preserve_nulls: bool = True
    additional_keywords: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        pii_map: Dict[str, Set[str]] = {}
        for table, cols in (self.pii_columns or {}).items():
            norm_table = _norm(table)
            pii_map.setdefault(norm_table, set()).update({_norm(c) for c in cols})
        self._pii_map = pii_map
        self._keywords = _SENSITIVE_KEYWORDS | {k.lower() for k in self.additional_keywords}

    def should_mask(self, column: str, tables: Sequence[str] | None = None) -> bool:
        col_norm = _norm(column)
        if not col_norm:
            return False

        tables = tables or []
        for table in tables:
            tab_norm = _norm(table)
            tab_cols = self._pii_map.get(tab_norm)
            if tab_cols and col_norm in tab_cols:
                return True

        # Global overrides (table-agnostic)
        if "" in self._pii_map and col_norm in self._pii_map[""]:
            return True

        # Heuristic fallback based on column naming
        for keyword in self._keywords:
            if keyword and keyword in col_norm:
                return True
        return False

    def mask_value(self, value: Any) -> Any:
        if value is None:
            return None if self.preserve_nulls else self.mask_token
        if isinstance(value, (int, float)):
            return self.mask_token
        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                return value
            if len(trimmed) <= 4:
                return self.mask_token
            return f"{trimmed[:2]}{self.mask_token}{trimmed[-2:]}"
        if isinstance(value, (bytes, bytearray)):
            return self.mask_token
        return self.mask_token


def mask_row(
    row: Mapping[str, Any],
    columns: Sequence[str] | Sequence[Mapping[str, Any]] | None,
    policy: MaskingPolicy,
    *,
    tables: Sequence[str] | None = None,
    expose: bool = False,
) -> Dict[str, Any]:
    """Return a masked copy of ``row`` according to ``policy``.

    Parameters
    ----------
    row:
        Mapping of column name to value.
    columns:
        Either a list of column names or column metadata dictionaries. Used to
        preserve output ordering when constructed from ``zip`` operations.
    policy:
        Masking policy describing PII columns and token.
    tables:
        Optional fully-qualified table names involved in the query.
    expose:
        When ``True``, returns ``row`` unchanged (privileged path).
    """

    if expose:
        return dict(row)

    # Normalise column names supplied
    col_names: Sequence[str]
    if columns and isinstance(columns[0], Mapping):  # type: ignore[index]
        col_names = [
            str(c.get("name") or c.get("column") or c.get("ColumnName") or "")
            for c in columns  # type: ignore[assignment]
        ]
    elif columns:
        col_names = [str(c) for c in columns]
    else:
        col_names = list(row.keys())

    masked: Dict[str, Any] = dict(row)
    for col in col_names:
        norm_col = str(col)
        if policy.should_mask(norm_col, tables):
            masked[norm_col] = policy.mask_value(masked.get(norm_col))
    # Ensure any additional keys (not in columns) are evaluated too
    for col, value in row.items():
        if col not in masked:
            masked[col] = value
        elif policy.should_mask(col, tables):
            masked[col] = policy.mask_value(value)
    return masked


def mask_rows(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str] | Sequence[Mapping[str, Any]] | None,
    policy: MaskingPolicy,
    *,
    tables: Sequence[str] | None = None,
    expose: bool = False,
) -> list[Dict[str, Any]]:
    return [mask_row(row, columns, policy, tables=tables, expose=expose) for row in rows]
