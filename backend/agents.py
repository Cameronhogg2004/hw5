"""The Campus Customs agent team: boss, inventory, accounting, facilities, customer_service.

* PydanticAI agents, all on gpt-5.6-luna through Portkey.
* Shop facts come only from the MCP server (each agent sees a filtered tool list).
* Full connectivity: every agent has `delegate` and can hand work to any teammate.
  Loop guards: no delegating to yourself or to anyone already up your call chain,
  depth <= MAX_DEPTH, and MAX_DELEGATIONS per ticket.
* Every agent-loop step (model output, tool call, tool result, delegation, final report)
  is appended to output/audit_trail.json.
"""
from __future__ import annotations

from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage, UsageLimits

import audit
from config import (MAX_DELEGATIONS, MAX_DEPTH, MAX_OUTPUT_TOKENS, MODEL_NAME, PORTKEY_API_KEY, PORTKEY_BASE_URL,
                    PROMPTS_DIR, REQUEST_LIMIT, TOOL_CALLS_LIMIT, TOTAL_TOKENS_LIMIT)
from mcp_link import AGENT_TOOLS, toolset_for
from models import AGENT_NAMES, AgentName, AgentReport, BossReport, RunState, TeamDeps

if not PORTKEY_API_KEY:
    raise RuntimeError("PORTKEY_API_KEY is missing. Add it to the course-root .env file.")

_client = AsyncOpenAI(api_key=PORTKEY_API_KEY, base_url=PORTKEY_BASE_URL,
                      default_headers={"x-portkey-api-key": PORTKEY_API_KEY})
model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=_client))
SETTINGS = OpenAIResponsesModelSettings(max_tokens=MAX_OUTPUT_TOKENS, openai_reasoning_effort="low")
LIMITS = UsageLimits(request_limit=REQUEST_LIMIT, tool_calls_limit=TOOL_CALLS_LIMIT,
                     total_tokens_limit=TOTAL_TOKENS_LIMIT)

ROLE_LINE = {
    "boss": "desk lead; routes the ticket and closes it out",
    "inventory": "stock, sizes, vendors, lead times, restock purchase orders",
    "accounting": "cash, invoices, preparing payments for approval, pricing and bulk quotes",
    "facilities": "the shop lease, landlord, rent and due dates",
    "customer_service": "customer reply drafts that stay on the board (never sent)",
}


async def delegate(ctx: RunContext[TeamDeps], to_agent: AgentName, task: str) -> str:
    """Hand a self-contained task to a teammate and get their report back.

    Include the ticket id and every fact they need (sku, size, qty, invoice id, lease id, amounts).
    """
    d = ctx.deps
    path = " -> ".join([*d.chain, d.me])
    if to_agent == d.me:
        return "Refused: you can't delegate to yourself."
    if to_agent in d.chain:
        return (f"Refused: {to_agent} is already waiting on you ({path}). Finish with what you have and report "
                "back instead of delegating upward.")
    if d.depth + 1 > MAX_DEPTH:
        return f"Refused: delegation depth limit ({MAX_DEPTH}) reached on {path}. Report back with what you have."
    if d.state.delegations >= MAX_DELEGATIONS:
        return f"Refused: this ticket already used its {MAX_DELEGATIONS} delegations. Report back with what you have."
    d.state.delegations += 1
    _event(d, "delegation", to_agent=to_agent, task=task)
    report = await run_agent(to_agent, task, TeamDeps(me=to_agent, chain=[*d.chain, d.me], state=d.state),
                             usage=ctx.usage)
    return report.model_dump_json()


def _build(name: str) -> Agent:
    agent = Agent(
        model,
        name=name,
        deps_type=TeamDeps,
        output_type=BossReport if name == "boss" else AgentReport,
        instructions=(PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8"),
        toolsets=[toolset_for(name)],
        tools=[delegate],
        model_settings=SETTINGS,
        retries=2,
    )

    @agent.instructions
    def run_context(ctx: RunContext[TeamDeps]) -> str:
        d = ctx.deps
        asked_by = d.chain[-1] if d.chain else "Cameron, from the board"
        others = "\n".join(f"- {n}: {ROLE_LINE[n]}" for n in AGENT_NAMES if n != d.me)
        return (f"## This run\nTicket: {d.state.ticket_id}. You are `{d.me}`. Asked by: {asked_by}. "
                f"Call chain: {' -> '.join([*d.chain, d.me])}.\n"
                f"Your MCP tools: {', '.join(sorted(AGENT_TOOLS[d.me]))}, plus `delegate`.\n"
                f"Teammates you can delegate to (not anyone already in your call chain):\n{others}")

    return agent


AGENTS: dict[str, Agent] = {n: _build(n) for n in AGENT_NAMES}


def _event(d: TeamDeps, kind: str, **data) -> dict:
    d.state.step += 1
    return audit.append({"run_id": d.state.run_id, "ticket_id": d.state.ticket_id, "step": d.state.step,
                         "agent": d.me, "depth": d.depth, "chain": [*d.chain, d.me], "kind": kind, **data})


def _record(d: TeamDeps, node) -> None:
    """One audit entry per thing that happened in this agent-loop step."""
    if Agent.is_call_tools_node(node):
        resp = node.model_response
        tokens = {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens}
        for part in resp.parts:
            if isinstance(part, TextPart) and part.content.strip():
                _event(d, "said", text=audit.clip(part.content, 2000), tokens=tokens)
            elif isinstance(part, ToolCallPart) and part.tool_name not in ("delegate", "final_result"):
                _event(d, "tool_call", tool=part.tool_name, args=part.args_as_dict(), tokens=tokens)
    elif Agent.is_model_request_node(node):
        for part in node.request.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name not in ("delegate", "final_result"):
                _event(d, "tool_result", tool=part.tool_name, result=audit.clip(part.content))
            elif isinstance(part, ToolReturnPart) and part.tool_name == "delegate":
                _event(d, "delegation_result", result=audit.clip(part.content, 2500))
            elif isinstance(part, RetryPromptPart):
                _event(d, "retry", tool=part.tool_name, detail=audit.clip(part.model_response(), 600))


async def run_agent(name: str, task: str, deps: TeamDeps, usage: RunUsage):
    _event(deps, "task", task=task, asked_by=deps.chain[-1] if deps.chain else "board")
    async with AGENTS[name].iter(task, deps=deps, usage=usage, usage_limits=LIMITS) as run:
        async for node in run:
            _record(deps, node)
    output = run.result.output
    deps.state.reports.setdefault(name, []).append(output.model_dump())
    _event(deps, "report", report=output.model_dump(),
           usage_so_far={"requests": usage.requests, "tool_calls": usage.tool_calls,
                         "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens})
    return output


async def run_team(ticket_id: int, run_id: str) -> tuple[BossReport, RunUsage, RunState]:
    state = RunState(run_id=run_id, ticket_id=ticket_id)
    usage = RunUsage()
    report = await run_agent(
        "boss",
        f"Ticket {ticket_id} just landed on the desk. Read it, bring in only the teammates it needs, "
        "and close it out with resolve_ticket.",
        TeamDeps(me="boss", chain=[], state=state),
        usage,
    )
    return report, usage, state
