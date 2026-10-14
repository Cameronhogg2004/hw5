"""Data types shared by the agents and the API."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[str, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")


class AgentReport(BaseModel):
    """What a specialist hands back to whoever delegated to it."""

    agent: AgentName
    summary: str = Field(description="2-3 sentences: what you found and did, with the real numbers.")
    facts_used: list[str] = Field(description="Facts you relied on, each tied to a tool or teammate.")
    actions: list[str] = Field(description="What you prepared or saved (approval ids, draft ids). Empty if none.")
    approvals_prepared: list[int] = Field(default_factory=list)
    drafts_created: list[int] = Field(default_factory=list)
    needs_human: str | None = Field(default=None, description="What Cameron must decide or click, if anything.")


class Contribution(BaseModel):
    agent: AgentName
    contribution: str


class BossReport(BaseModel):
    """The Boss's close-out for one ticket."""

    ticket_id: int
    called_first: AgentName
    why_first: str
    delegations: list[str] = Field(description="Each delegation as 'from -> to: task', in order.")
    outcome: str = Field(description="2-3 sentence outcome of the ticket.")
    contributions: list[Contribution]
    approvals_waiting: list[int] = Field(default_factory=list)


@dataclass
class RunState:
    """Shared by every agent in one ticket run."""

    run_id: str
    ticket_id: int
    delegations: int = 0
    step: int = 0
    reports: dict[str, list[dict]] = field(default_factory=dict)


@dataclass
class TeamDeps:
    """Per-agent context: who I am, who asked me (the chain), and the shared run state."""

    me: str
    chain: list[str]
    state: RunState

    @property
    def depth(self) -> int:
        return len(self.chain)


class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1, max_length=60)


class DeclineBody(BaseModel):
    declined_by: str = Field(min_length=1, max_length=60)
    note: str = Field(default="Declined on the board", max_length=300)
