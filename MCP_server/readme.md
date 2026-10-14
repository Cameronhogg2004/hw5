# Campus Customs MCP server

This is the one doorway to the shop's data. Every agent on the team (boss, inventory, accounting, facilities, customer service), the FastAPI backend, and the vibe coder (through `.mcp.json`) get shop facts and make changes through these tools. Nothing invents data. Every answer is a row from the database.

- **Built with:** FastMCP, stdio transport. Run with `.venv/bin/python MCP_server/server.py`.
- **Database:** `data/campus_customs_new.db` (the working copy). You can override it with `CAMPUS_DB`. The server refuses to open the original `data/campus_customs.db`, which stays untouched so the shop can be reset.
- **Today:** every overdue / due-soon calculation uses `desk.date_today`, not the real clock.

## Tools

**Started in Problem 3 (one for each open ticket)**
- `check_inventory(sku, size)` — units on hand and aisle (101: tee S; 103: hoodie M).
- `get_invoice(invoice_id)` — invoice, vendor, days overdue, whether it blocks shipping (101: invoice 501).
- `get_lease(lease_id)` — rent, landlord, next due date, days until due (102: lease 1).

**Added in Problem 5 for the agent team**
- Reading: `list_tickets`, `get_ticket`, `get_desk_date`, `get_pricing`, `list_open_invoices`, `list_vendors`, `check_vendor_can_ship`, `get_cash_balance`, `list_payments`, `list_pending_approvals`, `list_approvals`, `list_drafts`, `quote_bulk_price`.
- Preparing (no money moves): `prepare_invoice_payment`, `prepare_rent_payment`, `prepare_purchase_order`, `create_draft_reply`, `resolve_ticket`, `set_ticket_status`.
- Human only: `execute_approved_payment` (the pay tool) and `decline_approval`. Both need the backend's human-gate token, which only exists after someone clicks Approve or Decline on the board. The pay tool refuses if checking can't cover the amount (no negative balances), if a purchase's vendor still has an open invoice, or if the approver is an agent.

## Tables it adds to the working copy

`approvals`, `purchase_orders`, `drafts`, `ticket_resolutions`. They're created automatically, including after a reset. The shop's original tables keep their columns. Their values change only through the tools above.
