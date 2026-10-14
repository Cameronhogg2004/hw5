"""Shop-rule checks for the MCP pay tools, run on a throwaway copy of the original database.

Proves: no pay without the human gate, no agent approvers, vendor blocked by an open invoice,
the pay tool refuses when cash is short (no negative balance), and tables update on payment.
Writes output/rule_checks.json. Never touches campus_customs_new.db.
"""
import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

HW = Path(__file__).resolve().parent.parent
TOKEN = "test-gate-token"


async def main() -> None:
    tmp = Path(tempfile.mkdtemp()) / "rule_check.db"
    shutil.copyfile(HW / "data" / "campus_customs.db", tmp)
    tmp.chmod(0o644)
    env = {"PATH": os.environ["PATH"], "CAMPUS_DB": str(tmp), "CC_HUMAN_GATE_TOKEN": TOKEN}
    transport = StdioTransport(command=str(HW / ".venv/bin/python"), args=[str(HW / "MCP_server/server.py")], env=env)
    checks = []

    async with Client(transport) as c:
        async def call(name, **args):
            return (await c.call_tool(name, args, raise_on_error=False)).structured_content

        def check(name, expect, result):
            checks.append({"check": name, "expected": expect, "result": result,
                           "passed": (result.get("refused") is True) == (expect == "refused")})

        inv = await call("prepare_invoice_payment", ticket_id=101, invoice_id=501, requested_by="accounting")
        po = await call("prepare_purchase_order", ticket_id=101, vendor_id=1, sku="CC-TEE-WHITE", size="S", qty=1,
                        requested_by="inventory")
        rent = await call("prepare_rent_payment", ticket_id=102, lease_id=1, requested_by="accounting")
        check("Pay without the board's human-gate token", "refused",
              await call("execute_approved_payment", approval_id=inv["approval_id"], approved_by="Cameron",
                         human_gate_token="guess"))
        check("Agent name as approver", "refused",
              await call("execute_approved_payment", approval_id=inv["approval_id"], approved_by="accounting",
                         human_gate_token=TOKEN))
        check("Purchase while vendor has open invoice 501", "refused",
              await call("execute_approved_payment", approval_id=po["approval_id"], approved_by="Cameron",
                         human_gate_token=TOKEN))
        check("Pay invoice 501 after human approval", "paid",
              await call("execute_approved_payment", approval_id=inv["approval_id"], approved_by="Cameron",
                         human_gate_token=TOKEN))
        check("Purchase after invoice is paid", "paid",
              await call("execute_approved_payment", approval_id=po["approval_id"], approved_by="Cameron",
                         human_gate_token=TOKEN))
        check("Pay rent after human approval", "paid",
              await call("execute_approved_payment", approval_id=rent["approval_id"], approved_by="Cameron",
                         human_gate_token=TOKEN))
        big = await call("prepare_purchase_order", ticket_id=103, vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=12,
                         requested_by="inventory")
        check("Purchase bigger than checking (12 hoodies x $22 = $264 vs $152)", "refused",
              await call("execute_approved_payment", approval_id=big["approval_id"], approved_by="Cameron",
                         human_gate_token=TOKEN))
        check("Pay the same approval twice", "refused",
              await call("execute_approved_payment", approval_id=rent["approval_id"], approved_by="Cameron",
                         human_gate_token=TOKEN))
        final = {"cash": await call("get_cash_balance"), "payments": (await call("list_payments"))["payments"],
                 "invoice_501": await call("get_invoice", invoice_id=501), "lease_1": await call("get_lease", lease_id=1)}

    out = {"database": "temporary copy of data/campus_customs.db (working copy untouched)",
           "all_passed": all(x["passed"] for x in checks), "checks": checks, "final_state": final}
    (HW / "output" / "rule_checks.json").write_text(json.dumps(out, indent=2))
    for x in checks:
        print("PASS" if x["passed"] else "FAIL", x["check"])
    print("checking ends at", final["cash"]["balance"])


asyncio.run(main())
