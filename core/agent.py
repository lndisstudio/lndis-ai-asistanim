"""
Agent -- the planner/executor core.

Flow:  user request  ->  plan()  ->  (user approves)  ->  execute()  ->  audit log

Planning modes:
  1. LLM-powered (if Ollama or OpenAI available) -- smart, context-aware
  2. Keyword-based fallback -- deterministic, always works
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.models import Plan, Action, ActionStatus, PolicyDecision, ToolCall
from core.registry import ToolRegistry
from core.audit import AuditLogger
from core.llm import LLMAdapter, LLMResponse
from core.settings import Settings
from policy.policy_engine import PolicyEngine

from tools.file_read import FileReadTool
from tools.file_write import FileWriteTool
from tools.command_run import CommandRunTool
from tools.install_app import InstallAppTool
from tools.research_local import LocalResearchTool
from tools.research_web import WebResearchTool


# -- System prompt for LLM planning ----------------------------------------

SYSTEM_PROMPT = """You are the FULL AUTHORITY ADMINISTRATOR of this computer.
Your ONLY goal is to fulfill the user's request immediately using the tools provided.

CRITICAL RULES:
1. DO NOT WAIT FOR APPROVAL. DO NOT EXPLAIN HOW TO DO THINGS. DO THEM.
2. If the user wants a file on the Desktop or anywhere else, write it immediately.
3. If the user wants to run a program or script, use command_run or start it via powershell.
4. You have FULL PERMISSION to read, write, and execute.
5. You must act as a precise execution engine.
6. Use multipile steps if needed (e.g., search, then read, then write).

Response Format:
[
  {"tool": "tool_name", "args": {"arg1": "val1"}, "description": "Doing X"}
]

If no tool is absolutely necessary for a simple greeting, respond with:
[{"tool": "none", "args": {}, "description": "Ready"}]
"""


class Agent:
    """Orchestrates planning, approval, and execution of tool chains."""

    def __init__(self, policy_path: str | None = None, settings: Settings | None = None):
        # Settings (persistent config)
        self.settings = settings or Settings()

        # Core subsystems
        self.policy = PolicyEngine(policy_path)
        self.audit = AuditLogger()
        self.registry = ToolRegistry(self.policy)

        # LLM from settings
        self.llm = LLMAdapter.from_settings(self.settings)

        # Register all tools
        self.registry.register(FileReadTool(self.policy))
        self.registry.register(FileWriteTool(self.policy))
        self.registry.register(CommandRunTool(self.policy))
        self.registry.register(InstallAppTool(self.policy))
        self.registry.register(LocalResearchTool(self.policy))
        self.registry.register(WebResearchTool(self.policy))

        # Ensure workspace exists
        self.policy.workspace.mkdir(parents=True, exist_ok=True)

        # State
        self._current_plan: Plan | None = None

    def reload_llm(self) -> None:
        """Reload the LLM adapter from current settings (after /set changes)."""
        self.llm = LLMAdapter.from_settings(self.settings)

    # -- info ---------------------------------------------------------------

    @property
    def planning_mode(self) -> str:
        """Is the current adapter actually usable (not fallback)?"""
        if self.llm.provider_name == "none":
            return "keyword"
        return "llm"

    @property
    def _llm_available(self) -> bool:
        return self.llm.provider_name != "none" and self.llm.is_available()

    # -- planning -----------------------------------------------------------

    def plan(self, user_request: str) -> Plan:
        """
        Parse the user request and produce a Plan.
        Uses LLM if available, falls back to keyword parsing.
        """
        if self._llm_available:
            actions = self._plan_with_llm(user_request)
        else:
            actions = self._plan_with_keywords(user_request)

        p = Plan(
            user_request=user_request,
            summary=self._summarize(actions),
            actions=actions,
        )
        self._current_plan = p
        return p

    def _plan_with_llm(self, user_request: str) -> list[Action]:
        """Use the LLM to generate an intelligent plan."""
        tools_info = self.registry.list_for_planner()
        tools_text = json.dumps(tools_info, indent=2, ensure_ascii=False)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Available tools:\n{tools_text}\n\n"
                f"Workspace: {self.policy.workspace}\n\n"
                f"User request: {user_request}"
            )},
        ]

        response = self.llm.chat(messages, temperature=0.2, max_tokens=1500)

        # Try to parse LLM response as JSON
        actions = self._parse_llm_response(response, user_request)
        return actions

    def _parse_llm_response(self, response: LLMResponse, user_request: str) -> list[Action]:
        """Parse LLM response into Action objects."""
        # If LLM returned tool_calls directly (function calling)
        if response.tool_calls:
            actions = []
            for tc in response.tool_calls:
                actions.append(Action(
                    tool_call=ToolCall(tool_name=tc["name"], args=tc.get("args", {})),
                    description=f"{tc['name']}: {tc.get('args', {})}",
                ))
            return actions

        # Try to extract JSON from content
        content = response.content.strip()

        # Try to find JSON array in the response
        json_str = self._extract_json(content)
        if json_str:
            try:
                steps = json.loads(json_str)
                if isinstance(steps, list):
                    actions = []
                    for step in steps:
                        tool_name = step.get("tool", "")
                        if tool_name == "none":
                            # LLM says it can't fulfill the request
                            continue
                        args = step.get("args", {})
                        desc = step.get("description", f"{tool_name}")
                        actions.append(Action(
                            tool_call=ToolCall(tool_name=tool_name, args=args),
                            description=desc,
                        ))
                    if actions:
                        return actions
            except json.JSONDecodeError:
                pass

        # LLM gave a text response instead of JSON -- fallback to keywords
        return self._plan_with_keywords(user_request)

    def _extract_json(self, text: str) -> str | None:
        """Try to extract a JSON array from text (handles markdown code blocks)."""
        # Try: entire text is JSON
        stripped = text.strip()
        if stripped.startswith("["):
            return stripped

        # Try: markdown code block
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                p = part.strip()
                # Remove language hint (json, etc.)
                if p.startswith("json"):
                    p = p[4:].strip()
                if p.startswith("["):
                    return p

        return None

    def _plan_with_keywords(self, request: str) -> list[Action]:
        """Simple keyword parser fallback.  Deterministic, always works."""
        req = request.strip().lower()
        actions: list[Action] = []

        # read file
        if req.startswith("read ") or req.startswith("oku "):
            path = request.split(maxsplit=1)[1].strip()
            actions.append(Action(
                tool_call=ToolCall(tool_name="file_read", args={"path": path}),
                description=f"Read {path}",
            ))

        # write file (with desktop shortcuts)
        elif req.startswith("write ") or req.startswith("yaz ") or "masaüstünde" in req or "on desktop" in req:
            parts = request.split()
            path = "Desktop/note.txt" # default
            if "masaüstünde" in req:
                # "masaüstünde test.txt oluştur" -> find the filename
                for p in parts:
                    if "." in p: path = f"Desktop/{p}"; break
            elif "on desktop" in req:
                for p in parts:
                    if "." in p: path = f"Desktop/{p}"; break
            else:
                path = parts[1] if len(parts) > 1 else "untitled.txt"
            
            content = "Hello from Lndis AI"
            if "içeriği" in req or "with content" in req:
                 # simple extraction
                 content = request.split("content")[-1].strip() if "content" in req else request.split("içeriği")[-1].strip()

            actions.append(Action(
                tool_call=ToolCall(tool_name="file_write", args={"path": path, "content": content, "mode": "create"}),
                description=f"Write to {path}",
            ))

        # run command
        elif req.startswith("run ") or req.startswith("calistir "):
            cmd_str = request.split(maxsplit=1)[1].strip()
            cmd_parts = cmd_str.split()
            actions.append(Action(
                tool_call=ToolCall(tool_name="command_run", args={"command": cmd_parts}),
                description=f"Run: {cmd_str}",
            ))

        # install
        elif req.startswith("install ") or req.startswith("kur "):
            parts = request.split(maxsplit=2)
            package = parts[1] if len(parts) > 1 else ""
            import platform as _plat
            mgr = "winget" if _plat.system() == "Windows" else "apt"
            actions.append(Action(
                tool_call=ToolCall(tool_name="install_app", args={"manager": mgr, "package": package}),
                description=f"Install {package} via {mgr}",
            ))

        # search local
        elif req.startswith("search ") or req.startswith("ara "):
            query = request.split(maxsplit=1)[1].strip()
            actions.append(Action(
                tool_call=ToolCall(tool_name="research_local", args={"query": query}),
                description=f"Search workspace for '{query}'",
            ))

        # search web
        elif req.startswith("web "):
            query = request.split(maxsplit=1)[1].strip()
            actions.append(Action(
                tool_call=ToolCall(tool_name="research_web", args={"query": query}),
                description=f"Web search: {query}",
            ))

        # list directory
        elif req.startswith("list ") or req.startswith("listele ") or req.startswith("ls "):
            path = request.split(maxsplit=1)[1].strip()
            actions.append(Action(
                tool_call=ToolCall(tool_name="file_read", args={"path": path}),
                description=f"List {path}",
            ))

        else:
            # If no keywords match, it's NOT a tool call.
            actions.append(Action(
                tool_call=ToolCall(tool_name="none", args={}),
                description="Just chatting",
            ))

        return actions

    def _summarize(self, actions: list[Action]) -> str:
        if not actions:
            return "(no actions)"
        return " -> ".join(a.description for a in actions)

    # -- approval -----------------------------------------------------------

    @property
    def current_plan(self) -> Plan | None:
        return self._current_plan

    def approve(self) -> None:
        if self._current_plan:
            self._current_plan.approved = True

    # -- execution ----------------------------------------------------------

    def execute(self) -> Plan:
        """Run the current plan.  Must be approved first."""
        plan = self._current_plan
        if plan is None:
            raise RuntimeError("no plan to execute")
        if not plan.approved:
            raise RuntimeError("plan not approved -- call agent.approve() first")

        for action in plan.actions:
            self._run_action(action)

        self._current_plan = None
        return plan

    def _run_action(self, action: Action) -> None:
        tc = action.tool_call

        # Policy pre-check
        decision, reason = self.policy.evaluate(tc.tool_name, tc.args)
        action.policy_decision = decision
        action.policy_reason = reason

        if decision == PolicyDecision.DENY:
            action.status = ActionStatus.DENIED
            action.error = reason
            self.audit.log(
                tool_name=tc.tool_name,
                args=tc.args,
                policy_decision="deny",
                policy_reason=reason,
                error=reason,
            )
            return

        # Execute
        action.status = ActionStatus.RUNNING
        action.started_at = datetime.now(timezone.utc)
        t0 = time.perf_counter()

        try:
            decision_out, _, result = self.registry.call(tc.tool_name, tc.args)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            action.finished_at = datetime.now(timezone.utc)

            action.result = result
            if isinstance(result, dict) and not result.get("ok", True):
                action.status = ActionStatus.FAILED
                action.error = result.get("error", "unknown error")
            else:
                action.status = ActionStatus.COMPLETED

            self.audit.log(
                tool_name=tc.tool_name,
                args=tc.args,
                policy_decision="allow",
                policy_reason=reason,
                result=str(result)[:500],
                error=action.error,
                duration_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            action.status = ActionStatus.FAILED
            action.error = str(exc)
            self.audit.log(
                tool_name=tc.tool_name,
                args=tc.args,
                policy_decision="allow",
                policy_reason=reason,
                error=str(exc),
                duration_ms=elapsed_ms,
            )

    # -- direct tool call (bypasses plan flow; still policy-gated) ----------

    def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Directly call a tool -- useful for CLI one-offs."""
        decision, reason = self.policy.evaluate(tool_name, kwargs)
        if decision == PolicyDecision.DENY:
            return {"ok": False, "error": reason}

        t0 = time.perf_counter()
        _, _, result = self.registry.call(tool_name, kwargs)
        elapsed = int((time.perf_counter() - t0) * 1000)

        self.audit.log(
            tool_name=tool_name,
            args=kwargs,
            policy_decision=decision.value,
            policy_reason=reason,
            result=str(result)[:500],
            duration_ms=elapsed,
        )
        return result

    # -- info ---------------------------------------------------------------

    def list_tools(self) -> list[dict]:
        return self.registry.list_for_planner()
