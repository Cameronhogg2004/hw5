# Campus Customs · Battle Desk — AI for Managers, Homework 5

A five-agent back office for Campus Customs, a Yale merch shop. A **boss**, **inventory**, **accounting**, **facilities** and **customer service** agent (PydanticAI, all on `gpt-5.6-luna` through Portkey) work the shop's desk tickets. They use one **MCP server** over the shop database. A Fortnite-themed **React board** lets a human watch the squad and approve every payment.

## What's here

| Path | What it is |
|---|---|
| `MCP_server/server.py` | FastMCP server — the only way into the shop data (`data/campus_customs_new.db`) |
| `.mcp.json` | Connects the MCP server to the vibe coder (Claude Code) |
| `backend/agents.py`, `backend/prompts/*.md`, `backend/models.py` | The five agents, one prompt file each, shared data types |
| `backend/main.py` | FastAPI routes the board calls |
| `frontend/` | React + Vite + TypeScript "Battle Desk" board |
| `output/` | harness, smoke test, audit trail, expected-vs-actual ticket page, design notes, resolved tickets, screenshots |
| `tests/` | `mcp_smoke.py` (Problem 4) and `rule_checks.py` (pay-tool rules on a throwaway copy) |
| `AI_prompts.md` | My prompt log, one section per problem |

## Run it

1. Put the course `campus_customs.db` in `data/` (see `data/README.md`) and add `PORTKEY_API_KEY=...` to a `.env` in this folder or a parent folder.
2. Set up Python:
   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install --only-binary cryptography -r requirements.txt
   .venv/bin/python reset_db.py
   ```
3. Start the backend (port 8000):
   ```bash
   cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000
   ```
4. Start the board (port 5173):
   ```bash
   cd frontend && npm install && npm run dev
   ```
5. Open http://localhost:5173, pick a ticket, hit **Drop in**, and approve the supply drops. **Back to lobby** resets the working database to the original.

## Shop rules the code enforces

- `desk.date_today` is the shop's today. Vendor lead times come from `vendors`.
- A vendor won't ship while it has an open invoice (checked in the pay tool, not just the prompt).
- Agents only prepare payments. Only a human click on the board pays, using a gate token the agents never see.
- The pay tool refuses if checking can't cover the amount, so there are no negative balances. Cash only goes out.
- No emails or vendor calls. Customer replies are drafts that stay on the board.
- The original database is never written to.
