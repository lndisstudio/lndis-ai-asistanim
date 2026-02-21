"""
command_run — Execute a shell command with allowlist + dry-run + approval.
"""

from __future__ import annotations

import platform
import shlex
import subprocess
from typing import Any

from tools.base import Tool
from policy.policy_engine import PolicyEngine


class CommandRunTool(Tool):
    def __init__(self, policy: PolicyEngine):
        self._policy = policy

    @property
    def name(self) -> str:
        return "command_run"

    @property
    def description(self) -> str:
        return (
            "Run a shell command.  Only allowlisted commands are permitted.  "
            "Requires explicit user approval before execution."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "command": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Command as a list, e.g. ['dir', 'C:\\\\Users']",
            },
            "timeout": {"type": "integer", "description": "Timeout in seconds (max 120)", "default": 30},
        }

    def run(self, *, command: list[str] | None = None, timeout: int = 30, **_: Any) -> dict:
        if not command:
            return {"ok": False, "error": "empty command"}

        # Policy check
        ok, reason = self._policy.is_command_allowed(command)
        if not ok:
            return {"ok": False, "error": reason}

        # Cap timeout
        cfg_max = 120
        timeout = min(timeout, cfg_max)

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=(platform.system() == "Windows"),
            )
            return {
                "ok": True,
                "returncode": result.returncode,
                "stdout": result.stdout[:5000],       # cap output length
                "stderr": result.stderr[:2000],
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"command timed out after {timeout}s"}
        except FileNotFoundError:
            return {"ok": False, "error": f"command not found: {command[0]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def dry_run(self, *, command: list[str] | None = None, **_: Any) -> str:
        if not command:
            return "DENIED: empty command"
        ok, reason = self._policy.is_command_allowed(command)
        if not ok:
            return f"DENIED: {reason}"
        display = " ".join(command)
        return f"Would execute: {display}"
