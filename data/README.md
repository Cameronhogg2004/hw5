# data/

Put the course file here as `campus_customs.db` (the original shop database from the Homework 5 zip). It is not committed to this repo.

- `campus_customs.db` — the original. Never written to. Keep it read-only (`chmod 444`).
- `campus_customs_new.db` — the working copy that the MCP server, backend and agents use. Create or reset it with `.venv/bin/python reset_db.py`, or the board's **Back to lobby** button.
