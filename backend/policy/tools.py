"""
MCP tool allowlists by session verification state.

Names must match the MCP server tool identifiers (Meridian / order MCP).
"""

from __future__ import annotations

from typing import TypedDict

# --- Catalog: no account / PIN required --------------------------------------

PUBLIC_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "list_products",
        "get_product",
        "search_products",
    }
)

# --- Identity gate -----------------------------------------------------------

VERIFICATION_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "verify_customer_pin",
    }
)

# --- Account-scoped (customer_id, orders, etc.) -------------------------------

ACCOUNT_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "get_customer",
        "list_orders",
        "get_order",
        "create_order",
    }
)

ALL_TOOL_NAMES: frozenset[str] = PUBLIC_TOOL_NAMES | VERIFICATION_TOOL_NAMES | ACCOUNT_TOOL_NAMES


def allowed_tool_names(*, session_verified: bool) -> list[str]:
    """Return MCP tool names the model may call for this turn."""
    if session_verified:
        return sorted(ALL_TOOL_NAMES)
    return sorted(PUBLIC_TOOL_NAMES | VERIFICATION_TOOL_NAMES)


class _ToolFilterDict(TypedDict, total=False):
    allowed_tool_names: list[str]


def mcp_tool_filter(*, session_verified: bool) -> _ToolFilterDict:
    """Pass to ``MCPServerStreamableHttp(..., tool_filter=...)`` (static allowlist)."""
    return {"allowed_tool_names": allowed_tool_names(session_verified=session_verified)}
