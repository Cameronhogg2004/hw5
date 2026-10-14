"""Campus Customs MCP server (FastMCP, stdio).

Every agent, the FastAPI backend, and the vibe coder reach the shop through
these tools. All facts come from data/campus_customs_new.db (the working
copy); nothing is invented. The original data/campus_customs.db is never
opened.

Tool groups
  read      list_tickets, get_ticket, get_desk_date, check_inventory, get_pricing,
            get_invoice, list_open_invoices, list_vendors, check_vendor_can_ship,
            get_lease, get_cash_balance, list_payments, list_pending_approvals,
            list_drafts, quote_bulk_price
  prepare   prepare_invoice_payment, prepare_rent_payment, prepare_purchase_order,
            create_draft_reply, resolve_ticket, set_ticket_status
  human     execute_approved_payment, decline_approval  (need the backend's
            human-gate token, which no agent ever sees)
"""
from __future__ import annotations

import calendar
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastmcp import FastMCP

HW_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CAMPUS_DB", HW_DIR / "data" / "campus_customs_new.db")).resolve()
ORIGINAL_DB = (HW_DIR / "data" / "campus_customs.db").resolve()
if DB_PATH == ORIGINAL_DB:
    raise SystemExit("Refusing to open the original database. Point CAMPUS_DB at the working copy.")

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}
TICKET_STATUSES = {"open", "in_progress", "awaiting_approval", "resolved", "needs_owner"}

mcp = FastMCP(
    "campus-customs",
    instructions=(
        "Campus Customs shop tools over data/campus_customs_new.db. desk.date_today is the shop's "
        "today. Agents may read and prepare; only a human click in the backend can move money."
    ),
)


# --------------------------------------------------------------------------- helpers

@contextmanager
def db(write: bool = False):
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        # Workflow tables (approvals, purchase_orders, drafts, ticket_resolutions). Re-checked on
        # every connection so they come back after the working copy is reset from the original.
        conn.executescript(SCHEMA)
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if write:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                kind TEXT NOT NULL,              -- invoice | rent | purchase
                ref_id INTEGER,                  -- invoice id | lease id | purchase order id
                vendor_id INTEGER,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                details TEXT,                    -- JSON
                requested_by TEXT NOT NULL,
                status TEXT NOT NULL,            -- pending | paid | refused | declined
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,
                decision_note TEXT
            );
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                vendor_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                size TEXT NOT NULL,
                qty INTEGER NOT NULL,
                unit_cost REAL NOT NULL,
                total REAL NOT NULL,
                ordered_on TEXT,
                eta TEXT,
                status TEXT NOT NULL             -- awaiting_approval | ordered | declined
            );
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER NOT NULL,
                recipient TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                author_agent TEXT NOT NULL,
                status TEXT NOT NULL,            -- always 'draft - not sent'
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ticket_resolutions (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                recorded_by TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def desk_today(c: sqlite3.Connection) -> date:
    return date.fromisoformat(c.execute("SELECT date_today FROM desk").fetchone()["date_today"])


def add_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def money(x: float) -> float:
    return round(float(x), 2)


def refuse(reason: str, **extra) -> dict:
    return {"ok": False, "refused": True, "reason": reason, **extra}


def balance(c: sqlite3.Connection, account: str = "checking") -> float | None:
    r = c.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    return None if r is None else money(r["balance"])


def open_invoices_for(c: sqlite3.Connection, vendor_id: int) -> list[dict]:
    return rows(c.execute(
        "SELECT id, amount, due_date, status, description FROM invoices "
        "WHERE vendor_id = ? AND status = 'open' ORDER BY due_date", (vendor_id,)))


def gate_ok(token: str) -> bool:
    expected = os.environ.get("CC_HUMAN_GATE_TOKEN", "")
    return bool(expected) and token == expected


def ticket_exists(c: sqlite3.Connection, ticket_id: int) -> bool:
    return c.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is not None


# --------------------------------------------------------------------------- read tools

@mcp.tool
def list_tickets() -> dict:
    """List every desk ticket with its type, requester, subject and status (open / in_progress /
    awaiting_approval / resolved / needs_owner)."""
    with db() as c:
        t = rows(c.execute("SELECT id, type, requester, subject, status, created_at FROM tickets ORDER BY id"))
        return {"date_today": desk_today(c).isoformat(), "tickets": t}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Full ticket row plus the product's real name (for a sku), the lease or invoice it links to,
    and any drafts, approvals and resolutions already recorded for it."""
    with db() as c:
        t = c.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return refuse(f"No ticket {ticket_id} in the database.")
        out = {"ticket": dict(t), "date_today": desk_today(c).isoformat()}
        if t["sku"]:
            name = c.execute("SELECT name FROM inventory WHERE sku = ? LIMIT 1", (t["sku"],)).fetchone()
            out["product_name"] = name["name"] if name else None
        if t["invoice_id"] is not None:
            inv = c.execute("SELECT i.*, v.name AS vendor_name FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
                            "WHERE i.id = ?", (t["invoice_id"],)).fetchone()
            out["linked_invoice"] = dict(inv) if inv else None
        if t["lease_id"] is not None:
            ls = c.execute("SELECT * FROM leases WHERE id = ?", (t["lease_id"],)).fetchone()
            out["linked_lease"] = dict(ls) if ls else None
        out["approvals"] = rows(c.execute(
            "SELECT id, kind, ref_id, amount, description, status, requested_by, decided_by, decision_note "
            "FROM approvals WHERE ticket_id = ? ORDER BY id", (ticket_id,)))
        out["drafts"] = rows(c.execute(
            "SELECT id, recipient, subject, body, author_agent, status FROM drafts WHERE ticket_id = ? ORDER BY id",
            (ticket_id,)))
        out["resolutions"] = rows(c.execute(
            "SELECT status, summary, recorded_by, recorded_at FROM ticket_resolutions WHERE ticket_id = ? ORDER BY id",
            (ticket_id,)))
        return out


@mcp.tool
def get_desk_date() -> dict:
    """The shop's 'today' (desk.date_today). Use this, never the real clock, for overdue math."""
    with db() as c:
        r = c.execute("SELECT date_today, notes FROM desk").fetchone()
        return {"date_today": r["date_today"], "notes": r["notes"]}


@mcp.tool
def check_inventory(sku: str, size: str | None = None) -> dict:
    """Units on hand for a SKU (one size, or every size when size is omitted), with shelf location.
    Ticket 101 needs CC-TEE-WHITE size S; ticket 103 needs 20 of CC-HOOD-NAVY size M."""
    with db() as c:
        if size:
            found = rows(c.execute("SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
                                   (sku, size)))
        else:
            found = rows(c.execute("SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? ORDER BY size",
                                   (sku,)))
        if not found:
            return refuse(f"No inventory row for sku={sku!r} size={size!r}.")
        return {"sku": sku, "size": size, "rows": found, "in_stock": any(r["qty"] > 0 for r in found)}


@mcp.tool
def get_pricing(sku: str) -> dict:
    """Unit cost and list price for a SKU, with the per-unit margin at list price."""
    with db() as c:
        r = c.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if r is None:
            return refuse(f"No pricing row for sku={sku!r}.")
        return {**dict(r), "margin_per_unit": money(r["list_price"] - r["unit_cost"]),
                "margin_pct": round(100 * (r["list_price"] - r["unit_cost"]) / r["list_price"], 1)}


@mcp.tool
def get_invoice(invoice_id: int) -> dict:
    """One vendor invoice: amount, due date, status, vendor, and how many days overdue it is
    against desk.date_today. Ticket 101 links invoice 501."""
    with db() as c:
        r = c.execute("SELECT i.*, v.name AS vendor_name, v.specialty, v.lead_days FROM invoices i "
                      "JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?", (invoice_id,)).fetchone()
        if r is None:
            return refuse(f"No invoice {invoice_id}.")
        today = desk_today(c)
        days = (today - date.fromisoformat(r["due_date"])).days
        return {**dict(r), "date_today": today.isoformat(),
                "is_overdue": r["status"] == "open" and days > 0,
                "days_overdue": max(days, 0) if r["status"] == "open" else 0,
                "blocks_new_shipments": r["status"] == "open"}


@mcp.tool
def list_open_invoices(vendor_id: int | None = None) -> dict:
    """Every unpaid (status='open') invoice, optionally for one vendor, with overdue days."""
    with db() as c:
        today = desk_today(c)
        q = ("SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, i.due_date, i.description FROM invoices i "
             "JOIN vendors v ON v.id = i.vendor_id WHERE i.status = 'open'")
        found = rows(c.execute(q + (" AND i.vendor_id = ?" if vendor_id else "") + " ORDER BY i.due_date",
                               (vendor_id,) if vendor_id else ()))
        for r in found:
            r["days_overdue"] = max((today - date.fromisoformat(r["due_date"])).days, 0)
        return {"date_today": today.isoformat(), "open_invoices": found,
                "total_open": money(sum(r["amount"] for r in found))}


@mcp.tool
def list_vendors() -> dict:
    """All vendors with specialty, lead_days, and whether an open invoice currently blocks them."""
    with db() as c:
        vs = rows(c.execute("SELECT * FROM vendors ORDER BY id"))
        for v in vs:
            blocking = open_invoices_for(c, v["id"])
            v["open_invoice_ids"] = [b["id"] for b in blocking]
            v["can_ship"] = not blocking
        return {"vendors": vs}


@mcp.tool
def check_vendor_can_ship(vendor_id: int) -> dict:
    """Shop rule: a vendor will not ship while it has an unpaid open invoice. Returns can_ship,
    the blocking invoices, lead_days, and the ETA if ordered today (desk date + lead_days)."""
    with db() as c:
        v = c.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if v is None:
            return refuse(f"No vendor {vendor_id}.")
        blocking = open_invoices_for(c, vendor_id)
        today = desk_today(c)
        return {"vendor": dict(v), "can_ship": not blocking, "blocking_invoices": blocking,
                "date_today": today.isoformat(),
                "eta_if_ordered_today": (today + timedelta(days=v["lead_days"])).isoformat()}


@mcp.tool
def get_lease(lease_id: int) -> dict:
    """Lease row (space, landlord, monthly_rent, next_due) and days until rent is due against
    desk.date_today. Ticket 102 links lease 1."""
    with db() as c:
        r = c.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        if r is None:
            return refuse(f"No lease {lease_id}.")
        today = desk_today(c)
        days = (date.fromisoformat(r["next_due"]) - today).days
        return {**dict(r), "date_today": today.isoformat(), "days_until_due": days, "is_overdue": days < 0}


@mcp.tool
def get_cash_balance(account: str = "checking") -> dict:
    """Current balance of a cash account (default checking), plus money already promised to
    pending approvals so nobody double-counts cash."""
    with db() as c:
        r = c.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if r is None:
            return refuse(f"No cash account {account!r}.")
        pending = c.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM approvals WHERE status = 'pending'").fetchone()["s"]
        return {"account": r["name"], "balance": money(r["balance"]), "as_of": r["date"],
                "pending_approvals_total": money(pending),
                "balance_if_all_pending_paid": money(r["balance"] - pending)}


@mcp.tool
def list_payments() -> dict:
    """Every payment already made (kind, ref_id, amount, account, paid_at, approved_by)."""
    with db() as c:
        return {"payments": rows(c.execute("SELECT * FROM payments ORDER BY id"))}


@mcp.tool
def list_pending_approvals(ticket_id: int | None = None) -> dict:
    """Payments and purchases waiting for a human click, optionally for one ticket."""
    with db() as c:
        q = "SELECT * FROM approvals WHERE status = 'pending'"
        found = rows(c.execute(q + (" AND ticket_id = ?" if ticket_id else "") + " ORDER BY id",
                               (ticket_id,) if ticket_id else ()))
        for r in found:
            r["details"] = json.loads(r["details"] or "{}")
        return {"pending": found}


@mcp.tool
def list_approvals(ticket_id: int | None = None) -> dict:
    """Every approval request in any state (pending / paid / refused / declined)."""
    with db() as c:
        q = "SELECT * FROM approvals"
        found = rows(c.execute(q + (" WHERE ticket_id = ?" if ticket_id else "") + " ORDER BY id",
                               (ticket_id,) if ticket_id else ()))
        for r in found:
            r["details"] = json.loads(r["details"] or "{}")
        return {"approvals": found}


@mcp.tool
def list_drafts(ticket_id: int | None = None) -> dict:
    """Saved reply drafts. Drafts are never sent; they stay on the board for a human."""
    with db() as c:
        q = "SELECT * FROM drafts"
        return {"drafts": rows(c.execute(q + (" WHERE ticket_id = ?" if ticket_id else "") + " ORDER BY id",
                                         (ticket_id,) if ticket_id else ()))}


@mcp.tool
def quote_bulk_price(sku: str, qty: int, discount_pct: float) -> dict:
    """Price a bulk quote from the pricing table: unit price after discount, total, and margin.
    Refuses any discount that would sell below unit_cost."""
    with db() as c:
        r = c.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if r is None:
            return refuse(f"No pricing row for sku={sku!r}.")
        if qty <= 0 or not 0 <= discount_pct < 100:
            return refuse("qty must be positive and discount_pct between 0 and 100.")
        unit = money(r["list_price"] * (1 - discount_pct / 100))
        if unit < r["unit_cost"]:
            return refuse(f"{discount_pct}% off puts the price ({unit}) below unit_cost ({r['unit_cost']}).")
        return {"sku": sku, "qty": qty, "list_price": r["list_price"], "unit_cost": r["unit_cost"],
                "discount_pct": discount_pct, "unit_price": unit, "total": money(unit * qty),
                "list_total": money(r["list_price"] * qty), "customer_saves": money((r["list_price"] - unit) * qty),
                "margin_per_unit": money(unit - r["unit_cost"]),
                "margin_pct": round(100 * (unit - r["unit_cost"]) / unit, 1)}


# --------------------------------------------------------------------------- prepare tools (no money moves)

def _pending_exists(c, kind: str, ref_id: int) -> dict | None:
    r = c.execute("SELECT id FROM approvals WHERE kind = ? AND ref_id = ? AND status = 'pending'",
                  (kind, ref_id)).fetchone()
    return dict(r) if r else None


def _new_approval(c, *, ticket_id, kind, ref_id, vendor_id, amount, description, details, requested_by) -> dict:
    cur = c.execute(
        "INSERT INTO approvals (ticket_id, kind, ref_id, vendor_id, amount, description, details, requested_by, "
        "status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
        (ticket_id, kind, ref_id, vendor_id, money(amount), description, json.dumps(details), requested_by, now_iso()))
    bal = balance(c)
    return {"ok": True, "approval_id": cur.lastrowid, "status": "pending", "kind": kind, "amount": money(amount),
            "description": description, "checking_balance_now": bal,
            "cash_covers_it_now": bal is not None and bal >= amount,
            "next_step": "A human must click Approve on the board. No money has moved."}


@mcp.tool
def prepare_invoice_payment(ticket_id: int, invoice_id: int, requested_by: str) -> dict:
    """Queue an open vendor invoice for human approval. The amount comes from the invoice row.
    Does NOT pay anything."""
    with db(write=True) as c:
        if not ticket_exists(c, ticket_id):
            return refuse(f"No ticket {ticket_id}.")
        inv = c.execute("SELECT i.*, v.name AS vendor_name FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
                        "WHERE i.id = ?", (invoice_id,)).fetchone()
        if inv is None:
            return refuse(f"No invoice {invoice_id}.")
        if inv["status"] != "open":
            return refuse(f"Invoice {invoice_id} is already {inv['status']}.")
        if dup := _pending_exists(c, "invoice", invoice_id):
            return refuse(f"Invoice {invoice_id} already waits for approval as #{dup['id']}.", approval_id=dup["id"])
        return _new_approval(
            c, ticket_id=ticket_id, kind="invoice", ref_id=invoice_id, vendor_id=inv["vendor_id"],
            amount=inv["amount"], requested_by=requested_by,
            description=f"Pay invoice {invoice_id} to {inv['vendor_name']} (${inv['amount']:.2f}, due {inv['due_date']})",
            details={"vendor_name": inv["vendor_name"], "due_date": inv["due_date"], "invoice_description": inv["description"]})


@mcp.tool
def prepare_rent_payment(ticket_id: int, lease_id: int, requested_by: str) -> dict:
    """Queue the next rent payment on a lease for human approval. The amount is the lease's
    monthly_rent. Does NOT pay anything."""
    with db(write=True) as c:
        if not ticket_exists(c, ticket_id):
            return refuse(f"No ticket {ticket_id}.")
        ls = c.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        if ls is None:
            return refuse(f"No lease {lease_id}.")
        if dup := _pending_exists(c, "rent", lease_id):
            return refuse(f"Rent on lease {lease_id} already waits for approval as #{dup['id']}.", approval_id=dup["id"])
        return _new_approval(
            c, ticket_id=ticket_id, kind="rent", ref_id=lease_id, vendor_id=None, amount=ls["monthly_rent"],
            requested_by=requested_by,
            description=f"Pay rent for {ls['space_name']} to {ls['landlord']} (${ls['monthly_rent']:.2f}, due {ls['next_due']})",
            details={"landlord": ls["landlord"], "space_name": ls["space_name"], "due": ls["next_due"]})


@mcp.tool
def prepare_purchase_order(ticket_id: int, vendor_id: int, sku: str, size: str, qty: int, requested_by: str) -> dict:
    """Draft a restock order and queue its cost (qty x pricing.unit_cost) for human approval.
    The order only goes out after approval AND only if the vendor has no open invoice."""
    with db(write=True) as c:
        if not ticket_exists(c, ticket_id):
            return refuse(f"No ticket {ticket_id}.")
        v = c.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        p = c.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
        inv = c.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone()
        if v is None or p is None or inv is None:
            return refuse("Unknown vendor, sku or size.")
        if qty <= 0:
            return refuse("qty must be positive.")
        dup = c.execute("SELECT a.id FROM approvals a JOIN purchase_orders po ON po.id = a.ref_id "
                        "WHERE a.kind = 'purchase' AND a.status = 'pending' AND po.sku = ? AND po.size = ? "
                        "AND po.ticket_id = ?", (sku, size, ticket_id)).fetchone()
        if dup:
            return refuse(f"A purchase for {sku} {size} on ticket {ticket_id} already waits as #{dup['id']}.",
                          approval_id=dup["id"])
        total = money(p["unit_cost"] * qty)
        cur = c.execute("INSERT INTO purchase_orders (ticket_id, vendor_id, sku, size, qty, unit_cost, total, status) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 'awaiting_approval')",
                        (ticket_id, vendor_id, sku, size, qty, p["unit_cost"], total))
        blocking = open_invoices_for(c, vendor_id)
        today = desk_today(c)
        res = _new_approval(
            c, ticket_id=ticket_id, kind="purchase", ref_id=cur.lastrowid, vendor_id=vendor_id, amount=total,
            requested_by=requested_by,
            description=f"Order {qty} x {sku} size {size} from {v['name']} (${p['unit_cost']:.2f} each, lead {v['lead_days']} days)",
            details={"vendor_name": v["name"], "sku": sku, "size": size, "qty": qty, "unit_cost": p["unit_cost"],
                     "lead_days": v["lead_days"],
                     "eta_if_approved_today": (today + timedelta(days=v["lead_days"])).isoformat()})
        res["purchase_order_id"] = cur.lastrowid
        res["vendor_blocked_by_open_invoices"] = [b["id"] for b in blocking]
        if blocking:
            res["next_step"] += (f" The vendor is blocked until invoice(s) {[b['id'] for b in blocking]} are paid, "
                                 "so approve those first.")
        return res


@mcp.tool
def create_draft_reply(ticket_id: int, recipient: str, subject: str, body: str, author_agent: str) -> dict:
    """Save a reply draft on the board. It is NEVER emailed or sent; a human reviews it."""
    with db(write=True) as c:
        if not ticket_exists(c, ticket_id):
            return refuse(f"No ticket {ticket_id}.")
        cur = c.execute("INSERT INTO drafts (ticket_id, recipient, subject, body, author_agent, status, created_at) "
                        "VALUES (?, ?, ?, ?, ?, 'draft - not sent', ?)",
                        (ticket_id, recipient, subject, body, author_agent, now_iso()))
        return {"ok": True, "draft_id": cur.lastrowid, "status": "draft - not sent",
                "note": "Saved to the board only. Nothing was emailed."}


def _settle_ticket(c, ticket_id: int, recorded_by: str, summary: str | None = None) -> str:
    """Status follows the approvals: pending -> awaiting_approval, refused -> needs_owner, else resolved."""
    states = {r["status"] for r in c.execute("SELECT status FROM approvals WHERE ticket_id = ?", (ticket_id,))}
    status = "awaiting_approval" if "pending" in states else "needs_owner" if "refused" in states else "resolved"
    c.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
    if summary:
        c.execute("INSERT INTO ticket_resolutions (ticket_id, status, summary, recorded_by, recorded_at) "
                  "VALUES (?, ?, ?, ?, ?)", (ticket_id, status, summary, recorded_by, now_iso()))
    return status


@mcp.tool
def resolve_ticket(ticket_id: int, summary: str, recorded_by: str = "boss") -> dict:
    """Close out the team's work on a ticket. Status becomes awaiting_approval while a payment or
    purchase still needs a human click, needs_owner if the pay tool refused for cash, else resolved."""
    with db(write=True) as c:
        if not ticket_exists(c, ticket_id):
            return refuse(f"No ticket {ticket_id}.")
        return {"ok": True, "ticket_id": ticket_id, "status": _settle_ticket(c, ticket_id, recorded_by, summary)}


@mcp.tool
def set_ticket_status(ticket_id: int, status: str) -> dict:
    """Backend bookkeeping: mark a ticket open / in_progress while a run starts or fails."""
    if status not in {"open", "in_progress"}:
        return refuse("Only open or in_progress can be set directly; use resolve_ticket to close.")
    with db(write=True) as c:
        if not ticket_exists(c, ticket_id):
            return refuse(f"No ticket {ticket_id}.")
        c.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        return {"ok": True, "ticket_id": ticket_id, "status": status}


# --------------------------------------------------------------------------- human-gated tools

@mcp.tool
def execute_approved_payment(approval_id: int, approved_by: str, human_gate_token: str) -> dict:
    """THE PAY TOOL. Runs only after a human clicks Approve in the backend (needs the backend's
    human-gate token). Refuses if the cash is not there (no negative balances) or, for a purchase,
    if the vendor still has an open invoice. On success it writes payments, lowers checking and
    updates the invoice / lease / purchase order."""
    if not gate_ok(human_gate_token):
        return refuse("Human approval gate not satisfied. Only the board's Approve button can pay.")
    who = (approved_by or "").strip()
    if not who or who.lower() in AGENT_NAMES:
        return refuse("approved_by must be the human who clicked Approve, not an agent.")
    with db(write=True) as c:
        a = c.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if a is None:
            return refuse(f"No approval {approval_id}.")
        if a["status"] != "pending":
            return refuse(f"Approval {approval_id} is already {a['status']}.")
        today = desk_today(c).isoformat()
        bal = balance(c)
        amount = money(a["amount"])

        if a["kind"] == "purchase":
            blocking = open_invoices_for(c, a["vendor_id"])
            if blocking:
                return refuse(f"Vendor still has open invoice(s) {[b['id'] for b in blocking]}; it will not ship. "
                              "Approve the invoice payment first.", still_pending=True,
                              ticket_id=a["ticket_id"])
        if a["kind"] == "invoice":
            inv = c.execute("SELECT status FROM invoices WHERE id = ?", (a["ref_id"],)).fetchone()
            if inv is None or inv["status"] != "open":
                return refuse(f"Invoice {a['ref_id']} is no longer open.")

        if bal is None or bal < amount:
            c.execute("UPDATE approvals SET status = 'refused', decided_at = ?, decided_by = ?, decision_note = ? "
                      "WHERE id = ?", (now_iso(), who,
                                       f"Not enough cash: checking {bal:.2f} < {amount:.2f}. Owner must pay.", approval_id))
            if a["kind"] == "purchase":
                c.execute("UPDATE purchase_orders SET status = 'declined' WHERE id = ?", (a["ref_id"],))
            status = _settle_ticket(c, a["ticket_id"], "pay tool") if a["ticket_id"] else None
            return refuse(f"Not enough cash in checking ({bal:.2f}) for {amount:.2f}. No money moved; the owner "
                          "must pay this personally.", checking_balance=bal, ticket_id=a["ticket_id"],
                          ticket_status=status)

        new_bal = money(bal - amount)
        c.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = 'checking'", (new_bal, today))
        pay = c.execute("INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
                        "VALUES (?, ?, ?, 'checking', ?, ?)", (a["kind"], a["ref_id"], amount, today, who))
        effect = {}
        if a["kind"] == "invoice":
            c.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (a["ref_id"],))
            effect = {"invoice_id": a["ref_id"], "invoice_status": "paid"}
        elif a["kind"] == "rent":
            ls = c.execute("SELECT next_due FROM leases WHERE id = ?", (a["ref_id"],)).fetchone()
            nxt = add_month(date.fromisoformat(ls["next_due"])).isoformat()
            c.execute("UPDATE leases SET next_due = ?, notes = ? WHERE id = ?",
                      (nxt, f"Rent for {ls['next_due']} paid {today} (payment {pay.lastrowid}).", a["ref_id"]))
            effect = {"lease_id": a["ref_id"], "paid_period_due": ls["next_due"], "next_due": nxt}
        elif a["kind"] == "purchase":
            po = c.execute("SELECT po.*, v.lead_days FROM purchase_orders po JOIN vendors v ON v.id = po.vendor_id "
                           "WHERE po.id = ?", (a["ref_id"],)).fetchone()
            eta = (date.fromisoformat(today) + timedelta(days=po["lead_days"])).isoformat()
            c.execute("UPDATE purchase_orders SET status = 'ordered', ordered_on = ?, eta = ? WHERE id = ?",
                      (today, eta, po["id"]))
            effect = {"purchase_order_id": po["id"], "status": "ordered", "eta": eta,
                      "note": "Inventory rises when the delivery arrives, not today."}
        c.execute("UPDATE approvals SET status = 'paid', decided_at = ?, decided_by = ? WHERE id = ?",
                  (now_iso(), who, approval_id))
        status = _settle_ticket(c, a["ticket_id"], "pay tool") if a["ticket_id"] else None
        return {"ok": True, "approval_id": approval_id, "payment_id": pay.lastrowid, "kind": a["kind"],
                "amount": amount, "approved_by": who, "paid_at": today, "checking_before": bal,
                "checking_after": new_bal, "effect": effect, "ticket_id": a["ticket_id"], "ticket_status": status}


@mcp.tool
def decline_approval(approval_id: int, declined_by: str, note: str, human_gate_token: str) -> dict:
    """A human says no to a prepared payment or purchase. No money moves."""
    if not gate_ok(human_gate_token):
        return refuse("Human approval gate not satisfied.")
    with db(write=True) as c:
        a = c.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if a is None or a["status"] != "pending":
            return refuse(f"Approval {approval_id} is not pending.")
        c.execute("UPDATE approvals SET status = 'declined', decided_at = ?, decided_by = ?, decision_note = ? "
                  "WHERE id = ?", (now_iso(), declined_by, note, approval_id))
        if a["kind"] == "purchase":
            c.execute("UPDATE purchase_orders SET status = 'declined' WHERE id = ?", (a["ref_id"],))
        status = _settle_ticket(c, a["ticket_id"], declined_by) if a["ticket_id"] else None
        return {"ok": True, "approval_id": approval_id, "status": "declined", "ticket_status": status}



if __name__ == "__main__":
    mcp.run(show_banner=False)
