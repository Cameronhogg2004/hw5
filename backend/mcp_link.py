"""The one connection from the backend and agents to the Campus Customs MCP server.

Agents get filtered views of this toolset (only their role's tools). The backend
uses `call()` for board reads and, with the human-gate token, for approved payments.
The token lives only in this process and the MCP subprocess env; no model ever sees it.
"""
from __future__ import annotations

import json
import os
import secrets
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset

from config import DB_PATH, HW_DIR, MCP_SERVER, PYTHON

HUMAN_GATE_TOKEN = secrets.token_urlsafe(24)

_env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
_env.update({"CAMPUS_DB": str(DB_PATH), "CC_HUMAN_GATE_TOKEN": HUMAN_GATE_TOKEN})

shop_mcp = MCPToolset(
    Client(StdioTransport(command=str(PYTHON), args=[str(MCP_SERVER)], env=_env, cwd=str(HW_DIR))),
    id="campus-customs",
    max_retries=2,
)

# Least privilege: each role sees only these MCP tools. The pay tools are in nobody's list.
AGENT_TOOLS: dict[str, set[str]] = {
    "boss": {"get_ticket", "list_tickets", "get_desk_date", "get_cash_balance", "list_pending_approvals",
             "resolve_ticket"},
    "inventory": {"get_ticket", "check_inventory", "get_pricing", "list_vendors", "check_vendor_can_ship",
                  "prepare_purchase_order", "get_desk_date"},
    "accounting": {"get_ticket", "get_cash_balance", "get_invoice", "list_open_invoices", "prepare_invoice_payment",
                   "prepare_rent_payment", "list_pending_approvals", "list_payments", "get_pricing",
                   "quote_bulk_price", "get_desk_date"},
    "facilities": {"get_ticket", "get_lease", "get_desk_date", "get_cash_balance"},
    "customer_service": {"get_ticket", "check_inventory", "get_pricing", "create_draft_reply", "list_drafts"},
}
HUMAN_ONLY_TOOLS = {"execute_approved_payment", "decline_approval"}
assert not any(HUMAN_ONLY_TOOLS & tools for tools in AGENT_TOOLS.values())


def toolset_for(agent: str):
    allowed = AGENT_TOOLS[agent]
    return shop_mcp.filtered(lambda ctx, tool_def: tool_def.name in allowed)


def _plain(result: Any) -> Any:
    if isinstance(result, (dict, list)):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result
    return result


async def call(tool: str, args: dict | None = None) -> Any:
    """Backend-side MCP call (board reads, status bookkeeping)."""
    return _plain(await shop_mcp.direct_call_tool(tool, args or {}))


async def call_human(tool: str, args: dict) -> Any:
    """Only the approve/decline routes use this, after a human click."""
    assert tool in HUMAN_ONLY_TOOLS
    return _plain(await shop_mcp.direct_call_tool(tool, {**args, "human_gate_token": HUMAN_GATE_TOKEN}))
