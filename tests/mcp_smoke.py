"""Problem 4 smoke test: connect to the MCP server through .mcp.json and call the three
ticket tools, then cross-check every value against data/campus_customs_new.db."""
import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fastmcp import Client

HW = Path(__file__).resolve().parent.parent
DB = HW / "data" / "campus_customs_new.db"
OUT = HW / "output" / "mcp_smoke.json"

CASES = [
    {
        "prompt": "Use the campus-customs MCP tool check_inventory to see how many Classic Bulldog Tees "
                  "we have in size S for ticket 101.",
        "tool": "check_inventory", "args": {"sku": "CC-TEE-WHITE", "size": "S"},
        "sql": "SELECT qty, location FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S'",
        "pick": lambda r: {"qty": r["rows"][0]["qty"], "location": r["rows"][0]["location"]},
    },
    {
        "prompt": "Call get_invoice on invoice 501 (linked to ticket 101) and tell me if it is overdue "
                  "against the desk date.",
        "tool": "get_invoice", "args": {"invoice_id": 501},
        "sql": "SELECT amount, due_date, status, (SELECT date_today FROM desk) AS date_today FROM invoices WHERE id=501",
        "pick": lambda r: {"amount": r["amount"], "due_date": r["due_date"], "status": r["status"],
                           "date_today": r["date_today"]},
    },
    {
        "prompt": "Call get_lease on lease 1 (ticket 102) and tell me the rent and how many days until it is due.",
        "tool": "get_lease", "args": {"lease_id": 1},
        "sql": "SELECT monthly_rent, next_due, landlord FROM leases WHERE id=1",
        "pick": lambda r: {"monthly_rent": r["monthly_rent"], "next_due": r["next_due"], "landlord": r["landlord"]},
    },
]


async def main() -> None:
    config = json.loads((HW / ".mcp.json").read_text())
    for s in config["mcpServers"].values():  # .mcp.json uses project-relative paths
        s["command"] = str(HW / s["command"])
        s["args"] = [str(HW / a) for a in s["args"]]
        s["cwd"] = str(HW)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    results = []
    async with Client(config) as client:
        for case in CASES:
            res = await client.call_tool(case["tool"], case["args"])
            output = res.structured_content
            db_row = dict(conn.execute(case["sql"]).fetchone())
            picked = case["pick"](output)
            results.append({
                "prompt": case["prompt"], "tool": case["tool"], "args": case["args"], "tool_output": output,
                "db_check": {"query": case["sql"], "db_values": db_row, "tool_values": picked,
                             "matches": picked == db_row},
            })
    OUT.write_text(json.dumps({
        "ran_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database": "data/campus_customs_new.db",
        "connection": ".mcp.json -> campus-customs (stdio)",
        "results": results,
        "all_match": all(r["db_check"]["matches"] for r in results),
    }, indent=2))
    print("all_match:", all(r["db_check"]["matches"] for r in results))


asyncio.run(main())
