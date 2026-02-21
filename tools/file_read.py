"""
file_read — Read file content or list directory entries.
Policy-gated via policy_engine.is_path_allowed_read().
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from tools.base import Tool
from policy.policy_engine import PolicyEngine


class FileReadTool(Tool):
    def __init__(self, policy: PolicyEngine):
        self._policy = policy

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return "Read a file's contents or list a directory.  Read-only, no modifications."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "path": {"type": "string", "description": "Absolute path to file or directory"},
            "max_lines": {"type": "integer", "description": "Max lines to return (default 200)", "default": 200},
        }

    def run(self, *, path: str = "", max_lines: int = 200, **_: Any) -> dict:
        # Policy check
        ok, reason = self._policy.is_path_allowed_read(path)
        if not ok:
            return {"ok": False, "error": reason}

        target = Path(path).expanduser().resolve()

        if not target.exists():
            return {"ok": False, "error": f"path does not exist: {target}"}

        # Directory listing
        if target.is_dir():
            entries = []
            try:
                for child in sorted(target.iterdir()):
                    kind = "dir" if child.is_dir() else "file"
                    size = child.stat().st_size if child.is_file() else None
                    entries.append({"name": child.name, "type": kind, "size": size})
            except PermissionError:
                return {"ok": False, "error": "permission denied"}
            return {"ok": True, "type": "directory", "path": str(target), "entries": entries}

        # File content
        if target.is_file():
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            lines.append(f"... (truncated at {max_lines} lines)")
                            break
                        lines.append(line.rstrip("\n"))
            except PermissionError:
                return {"ok": False, "error": "permission denied"}

            return {
                "ok": True,
                "type": "file",
                "path": str(target),
                "lines": len(lines),
                "content": "\n".join(lines),
            }

        return {"ok": False, "error": "unsupported path type"}

    def dry_run(self, *, path: str = "", **_: Any) -> str:
        ok, reason = self._policy.is_path_allowed_read(path)
        if not ok:
            return f"DENIED: {reason}"
        return f"Would read: {Path(path).resolve()}"
