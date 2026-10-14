# Campus Customs Harness — Homework 5

This is the map of everything the agent team stands on: the database, the MCP tools, the five agents, the API routes, the board, and the safety rules. I started it in Problem 2 and added to it in every problem after that.

**Files**
- `data/campus_customs.db` — the original shop database from the course zip. It's read-only on disk and the code never opens it, except to copy it during a reset.
- `data/campus_customs_new.db` — the working copy. The MCP server, the backend, and every agent read and write this file only.
- `reset_db.py` (or `POST /api/reset` / the board's **Back to lobby** button) copies the original back over the working copy before a fresh run.

---

## 1. Tables and fields (Problem 2)

| Table | Fields | Why it matters for the agents |
|---|---|---|
| `desk` | `date_today`, `notes` | The shop's "today" (2026-08-31). Every overdue or days-until-due calculation uses this date, never the real calendar. |
| `inventory` | `sku`, `name`, `size`, `qty`, `location` (PK sku+size) | What's on the shelf, by size. It shows ticket 101 can't be filled (tee S = 0) and ticket 103 can only be partly filled (hoodie M = 8 of 20). |
| `pricing` | `sku`, `unit_cost`, `list_price` | What a restock costs us and what the customer pays. Accounting uses it for the bulk-discount floor, and Inventory uses it to price a purchase order. |
| `vendors` | `id`, `name`, `specialty`, `lead_days` | Who makes what and how long they take. Lead times come only from here (Bulldog Print Co = 5 days). |
| `invoices` | `id`, `vendor_id`, `amount`, `due_date`, `status`, `description` | Money we owe vendors. An `open` invoice blocks that vendor from shipping anything new. Invoice 501 ($840, due 2026-08-28) is overdue and blocks the tee reprint. |
| `leases` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | The shop's rent. Ticket 102 is about lease 1 ($2,400 due 2026-09-02). After rent is paid, `next_due` moves forward a month. |
| `cash_accounts` | `name`, `balance`, `date` | The only money we have (checking = $3,400). Cash only goes out, and the pay tool refuses anything that would make it negative. |
| `payments` | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | Starts empty. Every payment gets a row here, with the human who approved it. This is the audit record for cash. |
| `tickets` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at` | The work queue. Each ticket links to the row it's about (an inventory sku/size, a lease, or an invoice). `status` drives the board. |

**How the three open tickets link to the other tables**

- **101 · customer_order · Tauhid Zaman · "Bulldog tee"** → `inventory` (CC-TEE-WHITE, S, qty 1 → 0 on hand) → `invoices` 501 via `invoice_id` (Bulldog Print Co, $840, overdue) → `vendors` 1 (apparel reprint, 5 days) → `pricing` (unit cost $8, list $28). To restock, the shop has to pay 501 first.
- **102 · rent_notice · Elm City Properties · "Rent due"** → `leases` 1 via `lease_id` (Chapel Street shop, $2,400, due 2026-09-02, 2 days after the desk date) → `cash_accounts` (can checking cover it?).
- **103 · price_override · Yale AI Club · "Bulk hoodie discount"** → `inventory` (CC-HOOD-NAVY, M → 8 on hand, 12 short) → `pricing` (cost $22, list $58) → `vendors` 1 for the shortage lead time.

**Workflow tables the MCP server adds to the working copy** (the shop's own tables keep their columns):
`approvals` (payments and purchases waiting for a human click), `purchase_orders` (restock orders and their ETAs), `drafts` (customer replies that stay on the board), `ticket_resolutions` (each close-out summary). These get recreated automatically after a reset.

---

## 2. The first three MCP tools (Problem 3)

| Tool | Table it reads | Ticket it unlocks | Why it's the right tool for that ticket |
|---|---|---|---|
| `check_inventory(sku, size)` | `inventory` | **101** and **103** | 101 asks for one CC-TEE-WHITE in S and this returns qty 0 in Aisle B, so it shows we can't fill the order and have to restock. 103 needs 20 CC-HOOD-NAVY in M, and this returns 8, which gives the 12-unit gap the quote has to be honest about. |
| `get_invoice(invoice_id)` | `invoices` + `vendors` + `desk` | **101** | 101 links invoice 501. The tool shows it's still `open`, 3 days overdue against desk date 2026-08-31, and owed to Bulldog Print Co, the only apparel vendor. That open invoice is the reason the tee can't be reprinted until it's paid. |
| `get_lease(lease_id)` | `leases` + `desk` | **102** | 102 is a rent notice for lease 1. The tool returns the $2,400 rent, landlord Elm City Properties, and `days_until_due = 2` from the desk date, which confirms the email's "due in 2 days" before anyone moves money. |

---

## 3. The five agents (Problem 5)

All five are PydanticAI agents on **gpt-5.6-luna through Portkey** (`backend/agents.py`). Each prompt is its own file in `backend/prompts/`. Every agent has a `delegate` tool, so any agent can hand work to any other one (full connectivity), with loop guards.

| Agent | Prompt | Owns | MCP tools it can call |
|---|---|---|---|
| **boss** | `boss.md` | Reads the ticket, picks who goes first, delegates only to the agents the ticket needs, closes it out | `get_ticket`, `list_tickets`, `get_desk_date`, `get_cash_balance`, `list_pending_approvals`, `resolve_ticket` |
| **inventory** | `inventory.md` | Stock, sizes, vendors, lead times, restock purchase orders | `get_ticket`, `check_inventory`, `get_pricing`, `list_vendors`, `check_vendor_can_ship`, `prepare_purchase_order`, `get_desk_date` |
| **accounting** | `accounting.md` | Cash, invoices, preparing invoice and rent payments, pricing and bulk quotes | `get_ticket`, `get_cash_balance`, `get_invoice`, `list_open_invoices`, `prepare_invoice_payment`, `prepare_rent_payment`, `list_pending_approvals`, `list_payments`, `get_pricing`, `quote_bulk_price`, `get_desk_date` |
| **facilities** | `facilities.md` | Lease, landlord, rent amount and due date. Hands the payment to accounting | `get_ticket`, `get_lease`, `get_desk_date`, `get_cash_balance` |
| **customer_service** | `customer_service.md` | The customer's reply, saved as a draft that's never sent | `get_ticket`, `check_inventory`, `get_pricing`, `create_draft_reply`, `list_drafts` |

Data types are in `backend/models.py`: `AgentReport` (what a specialist returns), `BossReport` (who went first and why, the delegations, each agent's contribution, the approvals waiting), `TeamDeps`/`RunState` (call chain and shared run state).

**Audit trail.** `output/audit_trail.json` is an append-only JSON array. Every step in every agent's loop adds an entry: `task`, `tool_call` (tool + args), `tool_result`, `said`, `delegation`, `delegation_result`, `report`. Each entry carries `run_id`, `ticket_id`, `agent`, `step`, `depth`, `chain`, a timestamp, and token counts. The board adds `run_start`/`run_end`/`run_error`, `human_approval`/`human_decline`, and `reset`. Nothing ever wipes the file.

---

## 4. Every MCP tool (Problem 5)

Server: `MCP_server/server.py` (FastMCP, stdio). Database: `data/campus_customs_new.db`.

| Tool | Tables | Who calls it | What it's for |
|---|---|---|---|
| `list_tickets` | tickets, desk | boss, backend | The board's ticket list |
| `get_ticket` | tickets, inventory, invoices, vendors, leases, approvals, drafts, ticket_resolutions | all agents, backend | The ticket plus its product name, the invoice or lease it links to, and the work done so far |
| `get_desk_date` | desk | boss, inventory, accounting, facilities | The shop's today |
| `check_inventory` | inventory | inventory, customer_service | Units on hand by size (101, 103) |
| `get_pricing` | pricing | inventory, accounting, customer_service | Unit cost and list price |
| `get_invoice` | invoices, vendors, desk | accounting | Is invoice 501 open and overdue? (101) |
| `list_open_invoices` | invoices, vendors, desk | accounting | Every unpaid bill |
| `list_vendors` | vendors, invoices | inventory | Specialty, lead_days, can_ship |
| `check_vendor_can_ship` | vendors, invoices, desk | inventory | Enforces "no new shipment while an open invoice exists", plus the ETA |
| `get_lease` | leases, desk | facilities | Rent, landlord, days until due (102) |
| `get_cash_balance` | cash_accounts, approvals | boss, accounting, facilities, backend | Checking balance, plus cash already promised to pending approvals |
| `list_payments` | payments | accounting, backend | Payments made |
| `list_pending_approvals` / `list_approvals` | approvals | boss, accounting / backend | What's waiting for a human |
| `list_drafts` | drafts | customer_service, backend | Drafts on the board |
| `quote_bulk_price` | pricing | accounting | Discounted unit price, total, and margin. Refuses anything below cost (103) |
| `prepare_invoice_payment` | invoices, vendors, approvals | accounting | Queues invoice 501 for approval. **No money moves** |
| `prepare_rent_payment` | leases, approvals | accounting | Queues rent for approval. **No money moves** |
| `prepare_purchase_order` | vendors, pricing, inventory, purchase_orders, approvals | inventory | Drafts a restock order and queues qty × unit_cost for approval |
| `create_draft_reply` | drafts | customer_service | Saves a reply on the board. It's never sent |
| `resolve_ticket` | tickets, approvals, ticket_resolutions | boss | Closes the team's work. The status follows the approvals |
| `set_ticket_status` | tickets | backend | Sets open/in_progress when a run starts or fails |
| `execute_approved_payment` | approvals, cash_accounts, payments, invoices, leases, purchase_orders | **backend approve route only** | **The pay tool.** It needs the backend's human-gate token. It refuses if cash is short, if the vendor is still blocked, or if the approver is an agent. On success it writes `payments`, lowers checking, and marks the invoice paid / moves the lease due date / marks the PO ordered |
| `decline_approval` | approvals, purchase_orders | **backend decline route only** | A human says no |

---

## 5. Safety and token limits (Problem 5)

**Guardrails a real business would want when agents touch real customers and real money**

1. **Agents prepare, humans pay.** No agent has `execute_approved_payment` in its tool list, and the tool also needs a secret token that only the backend process holds. The model never sees it. The only way to move money is a person clicking **Approve** on the board, and their name goes into `payments.approved_by`.
2. **The pay tool refuses when cash is short.** It checks `cash_accounts.balance` inside one database transaction and won't go negative. If checking can't cover the bill, it refuses, nothing moves, and the ticket is marked `needs_owner` (I pay it myself).
3. **The vendor rule lives in the code, not just the prompt.** A purchase from a vendor with an open invoice is refused at pay time, so a confused agent can't get around it.
4. **Amounts come from the database, not the model.** Payment and purchase amounts come from the invoice, lease, or `qty × unit_cost`. An agent can't type a dollar figure into a payment.
5. **No outbound contact.** There's no email, SMS, or vendor-call tool anywhere. Customer replies are `drafts` with status `draft - not sent`, and they stay on the board.
6. **No invented data.** Every MCP tool returns rows from the working copy and refuses unknown ids. The prompts tell agents to say "I don't know" rather than guess. Customer drafts never show internal costs, vendor invoices, or our cash.
7. **Least privilege per role.** Each agent sees only its role's tools (for example, facilities can read the lease but can't prepare a payment, and customer service can't touch money).
8. **The original database is protected.** The MCP server refuses to open `campus_customs.db`, and the file is read-only on disk.
9. **Everything is auditable.** Every agent step and every human click is appended to `output/audit_trail.json` and never wiped.

**Limits that keep token use in check** (multi-agent chats burn tokens fast)

- One model everywhere: `gpt-5.6-luna`. No other model is configured or called.
- Shared `UsageLimits` per ticket run, across all five agents: 40 model requests, 60 tool calls, 400k total tokens. The run stops cleanly if it hits any of them.
- At most 6 delegations per ticket and a depth of 3. No delegating to yourself or back up your own call chain, so there are no ping-pong loops.
- `max_tokens` of 4,000 per response, and reasoning effort set to low.
- The boss prompt aims for 2–3 delegations and tells it not to send every specialist to every ticket. Every prompt says don't repeat a tool call for a fact you already have.
- Tool results in the audit trail are cut to about 1,500 characters.

---

## 6. API routes (Problem 7) — `backend/main.py`, http://localhost:8000

- `GET  /api/tickets` — the three tickets, whether each is open / in_progress / awaiting_approval / resolved, and how many approvals are pending.
- `GET  /api/tickets/{id}` — one ticket with its linked invoice/lease, approvals, drafts, resolutions, and the latest run's boss report.
- `POST /api/tickets/{id}/run` — starts the five-agent team on that ticket in the background and returns a `run_id`.
- `GET  /api/runs/{run_id}` — whether that run is still going, finished, or errored.
- `GET  /api/events?ticket_id=&run_id=&after=` — recent agent events (who said what, which tool they used, delegations) since the last reset, so the board can refresh.
- `GET  /api/agents` — the five agents and the MCP tools each one may use.
- `GET  /api/approvals?ticket_id=` — every prepared payment or purchase and its state.
- `POST /api/approvals/{id}/approve` — a human clicked Approve. Calls the pay tool, which moves cash or refuses. This is the only route that changes cash.
- `POST /api/approvals/{id}/decline` — a human said no. No money moves.
- `GET  /api/cash` — the current checking balance from `cash_accounts`, plus every payment made.
- `GET  /api/drafts?ticket_id=` — the reply drafts on the board.
- `POST /api/reset` — copies the original database back over the working copy for a fresh run (the audit trail is kept).
- `GET  /api/health` — up check. Shows the model and the database file in use.

---

## 7. The dashboard (Problems 8–9) — `frontend/`, http://localhost:5173

React + Vite + TypeScript, started with `npm run dev`. It only talks to the backend at `http://localhost:8000`, and the backend's CORS allows `localhost:5173` / `127.0.0.1:5173`. It's Fortnite-themed and drawn in pure HTML/CSS (see `output/design.md`).

- **Ticket loot cards** (`GET /api/tickets`): all three tickets with a plain status badge and how many approvals are pending.
- **Drop in** button (`POST /api/tickets/{id}/run`): starts the team on the picked ticket.
- **Squad**: one CSS character per agent showing what it's doing right now, its latest words or report, the tools it used, and who it delegated to. Active agents glow and benched agents are dimmed. A **live feed** shows every event (`GET /api/events`, polled every ~2 s).
- **Supply drops** (`POST /api/approvals/{id}/approve|decline`): the human approval step. The approver's name is saved in `payments.approved_by`.
- **Drafts**: sticky notes stamped NOT SENT. **Match summary**: the boss's outcome, who it called first and why, and one line per agent.
- **Bank** (`GET /api/cash`): the live checking balance, the pending total, and a ledger of payments. **Back to lobby** (`POST /api/reset`) resets the working database.
- `?ticket=101` in the URL preselects a ticket (that's how the screenshots in `output/resolved_board.html` were taken).

## 8. Safety rules (final)

Everything in §5 still holds. The full run proved these rules on the real working database:

| Rule | How it's enforced | Evidence |
|---|---|---|
| Human approval for every payment | Pay tool needs the backend's gate token, no agent has it, and approved_by can't be an agent name | `payments.approved_by = Cameron Hogg` ×3; `human_approval` entries in `audit_trail.json` |
| Update the right tables when paying | One transaction writes `payments`, `cash_accounts`, and `invoices` / `leases` / `purchase_orders` | Invoice 501 `paid`; lease 1 next_due 2026-10-02; PO 1 `ordered`, ETA 2026-09-05 |
| Vendor won't ship with an open invoice | `check_vendor_can_ship`, plus a re-check inside the pay tool | 101's PO was queued behind invoice 501; `rule_checks.json` shows the refusal when it's clicked first |
| Not enough cash → the pay tool refuses, I pay | Balance checked in the pay transaction; ticket set to `needs_owner` | `rule_checks.json`: 12 hoodies × $22 = $264 refused at $152 |
| No negative balances; cash only goes out | Same check; there's no revenue tool | $3,400 → $152, never below 0 (Cash tab) |
| `desk.date_today` is today | Every date calculation reads `desk` | Invoice 501 "3 days overdue", rent "due in 2 days" |
| No emails or vendor calls; drafts stay on the board | No outbound tools; `drafts.status = 'draft - not sent'` | Drafts #1 and #2 on the board |
| Only gpt-5.6-luna through Portkey | One `MODEL_NAME` in `backend/config.py` | `run_start` entries record the model |
| Reset before a full run | `POST /api/reset` / `reset_db.py` | `reset` entry (seq 173) just before the official run in `audit_trail.json` |
| Original database untouched | Read-only file; the server refuses to open it | `campus_customs.db` hash unchanged |

## 9. Full run record (Problem 9)

Reset → starting checking **$3,400.00** → 101 (Boss → Inventory → Accounting, Boss → Customer Service) → 102 (Boss → Facilities → Accounting) → I approved #1 $840, #2 $8, #3 $2,400 → 103 (Boss → Accounting → Inventory, Boss → Customer Service) → ending checking **$152.00** = `cash_accounts`. Details are in `output/desk_tickets.html` (Actual + Cash tabs), `output/resolved_tickets.json`, `output/resolved_board.html`, and `output/audit_trail.json` (entries after seq 173; earlier entries are my development test runs, kept because the trail is never wiped).
