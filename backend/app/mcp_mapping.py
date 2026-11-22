"""Maps the Financial Data Engine's MCP output to Contract A.

If the MCP tool already returns Contract A (it has "schema_version"), this is a pass-through.
If it returns its own shape, fill in `map_custom` once — this is the ONLY file that should change.
"""
from __future__ import annotations

from typing import Any


def to_contract_a(raw: Any, family_id: str) -> dict:
    if isinstance(raw, dict) and raw.get("schema_version"):
        return raw
    if isinstance(raw, dict) and "financial_records" in raw and "members" in raw:
        return {"schema_version": "1.0", "family_id": raw.get("family_id", family_id), **raw}
    return map_custom(raw, family_id)


def map_custom(raw: Any, family_id: str) -> dict:
    keys = list(raw)[:15] if isinstance(raw, dict) else type(raw).__name__
    raise ValueError(
        "MCP output is not in Contract A shape and no mapping is defined yet. "
        f"Top-level keys received: {keys}. Implement map_custom() in app/mcp_mapping.py."
    )
