"""Campus Customs desk API (FastAPI).

Run from backend/:  uvicorn main:app --reload --port 8000

Every shop fact goes through the MCP server (mcp_link). Agents only prepare payments;
the approve route is the only path that moves money, and only after a human click.
"""
from __future__ import annotations

import asyncio
import shutil
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import audit
import mcp_link
from config import DB_PATH, FRONTEND_ORIGINS, MODEL_NAME, ORIGINAL_DB
from models import AGENT_NAMES, ApproveBody, DeclineBody

RUNS: dict[str, dict] = {}            # run_id -> {ticket_id, state, report, error}
ACTIVE: dict[int, str] = {}           # ticket_id -> run_id while running
_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp_link.shop_mcp:     # one MCP server process shared by the API and every agent
        yield


app = FastAPI(title="Campus Customs Battle Desk API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def _latest_run(ticket_id: int) -> dict | None:
    runs = [r for r in RUNS.values() if r["ticket_id"] == ticket_id]
    if runs:
        return runs[-1]
    starts = [e for e in audit.read(ticket_id=ticket_id, after=_last_reset_seq())
              if e["kind"] in ("run_start", "run_end", "run_error")]
    if not starts:
        return None
    last = starts[-1]
    return {"run_id": last["run_id"], "ticket_id": ticket_id,
            "state": {"run_start": "running", "run_end": "finished", "run_error": "error"}[last["kind"]],
            "report": last.get("report"), "error": last.get("error")}


def _last_reset_seq() -> int:
    resets = [e["seq"] for e in audit.read() if e["kind"] == "reset"]
    return resets[-1] if resets else 0


# ------------------------------------------------------------------ tickets

@app.get("/api/tickets")
async def tickets():
    """The three tickets, their status, and pending approvals per ticket."""
    data = await mcp_link.call("list_tickets")
    pending = (await mcp_link.call("list_pending_approvals"))["pending"]
    for t in data["tickets"]:
        t["pending_approvals"] = sum(1 for p in pending if p["ticket_id"] == t["id"])
        t["running"] = t["id"] in ACTIVE
        run = _latest_run(t["id"])
        t["latest_run_id"] = run and run["run_id"]
    return data


@app.get("/api/tickets/{ticket_id}")
async def ticket_detail(ticket_id: int):
    """One ticket with its linked invoice/lease, approvals, drafts, resolutions and latest run."""
    data = await mcp_link.call("get_ticket", {"ticket_id": ticket_id})
    if data.get("refused"):
        raise HTTPException(404, data["reason"])
    data["latest_run"] = _latest_run(ticket_id)
    return data


@app.post("/api/tickets/{ticket_id}/run")
async def run_ticket(ticket_id: int):
    """Start the agent team on one ticket (runs in the background; poll /api/events)."""
    from agents import run_team  # imported here so the API still serves reads if the key is missing

    if ticket_id in ACTIVE:
        raise HTTPException(409, f"Ticket {ticket_id} is already running as {ACTIVE[ticket_id]}.")
    t = await mcp_link.call("get_ticket", {"ticket_id": ticket_id})
    if t.get("refused"):
        raise HTTPException(404, t["reason"])
    if t["ticket"]["status"] in ("resolved", "awaiting_approval"):
        raise HTTPException(409, f"Ticket {ticket_id} is {t['ticket']['status']}. Reset the database to rerun it.")

    run_id = f"run-{ticket_id}-{uuid.uuid4().hex[:6]}"
    RUNS[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "state": "running", "report": None, "error": None}
    ACTIVE[ticket_id] = run_id
    await mcp_link.call("set_ticket_status", {"ticket_id": ticket_id, "status": "in_progress"})
    cash = await mcp_link.call("get_cash_balance")
    audit.append({"run_id": run_id, "ticket_id": ticket_id, "kind": "run_start", "agent": "board",
                  "model": MODEL_NAME, "checking_at_start": cash["balance"]})

    async def work():
        try:
            report, usage, state = await run_team(ticket_id, run_id)
            after = await mcp_link.call("get_ticket", {"ticket_id": ticket_id})
            if after["ticket"]["status"] == "in_progress":   # boss forgot resolve_ticket: close it for them
                await mcp_link.call("resolve_ticket", {"ticket_id": ticket_id, "summary": report.outcome,
                                                       "recorded_by": "backend (boss did not call resolve_ticket)"})
            RUNS[run_id].update(state="finished", report=report.model_dump())
            audit.append({"run_id": run_id, "ticket_id": ticket_id, "kind": "run_end", "agent": "board",
                          "report": report.model_dump(), "delegations": state.delegations,
                          "usage": {"requests": usage.requests, "tool_calls": usage.tool_calls,
                                    "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}})
        except Exception as exc:  # usage limit, model or network error
            RUNS[run_id].update(state="error", error=f"{type(exc).__name__}: {exc}")
            audit.append({"run_id": run_id, "ticket_id": ticket_id, "kind": "run_error", "agent": "board",
                          "error": f"{type(exc).__name__}: {exc}"})
            await mcp_link.call("set_ticket_status", {"ticket_id": ticket_id, "status": "open"})
        finally:
            ACTIVE.pop(ticket_id, None)

    task = asyncio.create_task(work())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"run_id": run_id, "ticket_id": ticket_id, "state": "running"}


@app.get("/api/runs/{run_id}")
async def run_status(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404, "Unknown run.")
    return RUNS[run_id]


# ------------------------------------------------------------------ agent events

@app.get("/api/events")
async def events(ticket_id: int | None = None, run_id: str | None = None, after: int = 0, limit: int = 300,
                 since_reset: bool = True):
    """Recent agent events: who said what and which tool they used (from the audit trail)."""
    if since_reset:
        after = max(after, _last_reset_seq())
    found = audit.read(run_id=run_id, ticket_id=ticket_id, after=after)
    return {"events": found[-limit:], "last_seq": found[-1]["seq"] if found else after}


@app.get("/api/agents")
async def agents_info():
    """The five agents and the MCP tools each one may use."""
    return {"model": MODEL_NAME,
            "agents": [{"name": n, "tools": sorted(mcp_link.AGENT_TOOLS[n]) + ["delegate"]} for n in AGENT_NAMES]}


# ------------------------------------------------------------------ human approvals

@app.get("/api/approvals")
async def approvals(ticket_id: int | None = None):
    return await mcp_link.call("list_approvals", {"ticket_id": ticket_id} if ticket_id else {})


@app.post("/api/approvals/{approval_id}/approve")
async def approve(approval_id: int, body: ApproveBody):
    """A human clicked Approve. This is the only route that moves cash; the pay tool can still refuse."""
    result = await mcp_link.call_human("execute_approved_payment",
                                       {"approval_id": approval_id, "approved_by": body.approved_by})
    audit.append({"kind": "human_approval", "agent": "human", "approval_id": approval_id,
                  "approved_by": body.approved_by, "ticket_id": _ticket_of(result), "result": result})
    return result


@app.post("/api/approvals/{approval_id}/decline")
async def decline(approval_id: int, body: DeclineBody):
    result = await mcp_link.call_human("decline_approval", {"approval_id": approval_id,
                                                            "declined_by": body.declined_by, "note": body.note})
    audit.append({"kind": "human_decline", "agent": "human", "approval_id": approval_id,
                  "declined_by": body.declined_by, "result": result})
    return result


def _ticket_of(result: dict) -> int | None:
    return result.get("ticket_id") if isinstance(result, dict) else None


# ------------------------------------------------------------------ cash, drafts, reset

@app.get("/api/cash")
async def cash():
    """Current checking balance from cash_accounts, plus every payment made."""
    bal = await mcp_link.call("get_cash_balance")
    pays = await mcp_link.call("list_payments")
    return {**bal, "payments": pays["payments"]}


@app.get("/api/drafts")
async def drafts(ticket_id: int | None = None):
    return await mcp_link.call("list_drafts", {"ticket_id": ticket_id} if ticket_id else {})


@app.post("/api/reset")
async def reset():
    """Copy the original database back over the working copy for a fresh run. Audit trail is kept."""
    if ACTIVE:
        raise HTTPException(409, f"Wait for running tickets to finish: {sorted(ACTIVE)}")
    shutil.copyfile(ORIGINAL_DB, DB_PATH)
    DB_PATH.chmod(0o644)
    RUNS.clear()
    cash_now = await mcp_link.call("get_cash_balance")
    audit.append({"kind": "reset", "agent": "board", "detail": f"{DB_PATH.name} reset from {ORIGINAL_DB.name}",
                  "checking_after_reset": cash_now["balance"]})
    return {"ok": True, "checking": cash_now["balance"], "tickets": (await mcp_link.call("list_tickets"))["tickets"]}


@app.get("/api/health")
async def health():
    return {"ok": True, "model": MODEL_NAME, "database": DB_PATH.name}
