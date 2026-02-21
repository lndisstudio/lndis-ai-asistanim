"""
Dataclasses for Plans, Actions, ToolCalls, and AuditEntries.
These are the shared value objects used across the entire system.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


# ── Enums ──────────────────────────────────────────────────────────

class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"
    SKIPPED = "skipped"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


# ── ToolCall ───────────────────────────────────────────────────────

@dataclass
class ToolCall:
    """A single invocation of a tool with its arguments."""
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)


# ── Action ─────────────────────────────────────────────────────────

@dataclass
class Action:
    """One step inside a Plan.  Wraps a ToolCall + execution metadata."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    tool_call: ToolCall = field(default_factory=lambda: ToolCall(tool_name=""))
    description: str = ""
    status: ActionStatus = ActionStatus.PENDING
    result: Any = None
    error: str | None = None
    policy_decision: PolicyDecision | None = None
    policy_reason: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool": self.tool_call.tool_name,
            "args": self.tool_call.args,
            "description": self.description,
            "status": self.status.value,
            "result": str(self.result) if self.result is not None else None,
            "error": self.error,
            "policy_decision": self.policy_decision.value if self.policy_decision else None,
            "policy_reason": self.policy_reason,
        }


# ── Plan ───────────────────────────────────────────────────────────

@dataclass
class Plan:
    """A sequence of Actions the agent proposes for a user request."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_request: str = ""
    summary: str = ""
    actions: list[Action] = field(default_factory=list)
    approved: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_request": self.user_request,
            "summary": self.summary,
            "actions": [a.to_dict() for a in self.actions],
            "approved": self.approved,
            "created_at": self.created_at.isoformat(),
        }


# ── AuditEntry ─────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    """Immutable record of one tool execution for the audit trail."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    policy_decision: str = ""
    policy_reason: str = ""
    result: str = ""
    error: str | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "tool_name": self.tool_name,
            "args": self.args,
            "policy_decision": self.policy_decision,
            "policy_reason": self.policy_reason,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }
