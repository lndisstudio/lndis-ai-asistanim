"""
Tool Registry — register tools, list them for the planner, route calls.
"""

from __future__ import annotations
from typing import Any

from tools.base import Tool
from policy.policy_engine import PolicyEngine
from core.models import PolicyDecision


class ToolRegistry:
    """Central catalogue of available tools."""

    def __init__(self, policy: PolicyEngine):
        self._tools: dict[str, Tool] = {}
        self.policy = policy

    # ── registration ───────────────────────────────────────────────

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def list_for_planner(self) -> list[dict[str, Any]]:
        """Return tool metadata suitable for an LLM prompt."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    # ── call routing ───────────────────────────────────────────────

    def call(self, tool_name: str, args: dict[str, Any]) -> tuple[PolicyDecision, str, Any]:
        """
        Route a tool call through the policy engine, then execute.
        Returns (decision, reason, result_or_None).
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return PolicyDecision.DENY, f"tool '{tool_name}' not found", None

        decision, reason = self.policy.evaluate(tool_name, args)

        if decision == PolicyDecision.DENY:
            return decision, reason, None

        # REQUIRE_APPROVAL is handled by the agent layer (caller must
        # have obtained approval before reaching here).
        # If we get here for a require_approval tool, caller already approved.

        result = tool.run(**args)
        return PolicyDecision.ALLOW, reason, result
