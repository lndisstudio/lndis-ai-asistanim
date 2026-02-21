"""
research_web — Perform a web search.  
Hard-gated by the network toggle in the policy engine.
Returns "network disabled" when the toggle is off.
"""

from __future__ import annotations

from typing import Any

from tools.base import Tool
from policy.policy_engine import PolicyEngine


class WebResearchTool(Tool):
    def __init__(self, policy: PolicyEngine):
        self._policy = policy

    @property
    def name(self) -> str:
        return "research_web"

    @property
    def description(self) -> str:
        return (
            "Search the web for information.  Only works when the user "
            "has explicitly enabled network access.  Disabled by default."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "query": {"type": "string", "description": "Search query"},
        }

    def run(self, *, query: str = "", **_: Any) -> dict:
        ok, reason = self._policy.is_network_allowed()
        if not ok:
            return {"ok": False, "error": reason}

        if not query.strip():
            return {"ok": False, "error": "query is required"}

        # Minimal implementation — uses duckduckgo_search if available
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddg:
                raw = ddg.text(query, max_results=5)
                results = [
                    {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
                    for r in raw
                ]
            return {"ok": True, "query": query, "results": results}
        except ImportError:
            return {
                "ok": False,
                "error": "duckduckgo_search package not installed.  pip install duckduckgo_search",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def dry_run(self, *, query: str = "", **_: Any) -> str:
        ok, reason = self._policy.is_network_allowed()
        if not ok:
            return f"DENIED: {reason}"
        return f"Would search web for: {query}"
