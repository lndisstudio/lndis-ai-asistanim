"""
file_write — Write content to a file inside the workspace only.
Creates parent directories automatically.  Optional auto-backup.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.base import Tool
from policy.policy_engine import PolicyEngine


class FileWriteTool(Tool):
    def __init__(self, policy: PolicyEngine):
        self._policy = policy

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return "Write or append content to a file.  Writes are restricted to the workspace directory."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "path": {"type": "string", "description": "File path (relative paths are resolved inside workspace)"},
            "content": {"type": "string", "description": "Content to write"},
            "mode": {"type": "string", "enum": ["create", "overwrite", "append"], "default": "create"},
        }

    def run(self, *, path: str = "", content: str = "", mode: str = "create", **_: Any) -> dict:
        # Smart path resolution
        raw_path = str(path).lower()
        
        # Shortcuts for common directories
        shortcuts = {
            "desktop": Path.home() / "Desktop",
            "masaüstü": Path.home() / "Desktop",
            "documents": Path.home() / "Documents",
            "belgeler": Path.home() / "Documents",
            "downloads": Path.home() / "Downloads",
            "indirilenler": Path.home() / "Downloads",
        }

        target_path = Path(path)
        for key, p in shortcuts.items():
            if path.lower() == key or path.lower().startswith(f"{key}/") or path.lower().startswith(f"{key}\\"):
                # Handle "Desktop", "Desktop/test.txt" etc.
                if path.lower() == key:
                    return {"ok": False, "error": f"Path is a directory: {p}"}
                suffix = path[len(key)+1:]
                target_path = (p / suffix).resolve()
                break

        if not target_path.is_absolute():
            target = (self._policy.workspace / target_path).resolve()
        else:
            target = target_path.resolve()

        # Policy check
        ok, reason = self._policy.is_path_allowed_write(str(target))
        if not ok:
            return {"ok": False, "error": reason}

        # Mode checks
        if mode == "create" and target.exists():
            return {"ok": False, "error": "file already exists (use mode='overwrite' or 'append')"}

        # Auto-backup before overwrite
        if mode == "overwrite" and target.exists():
            backup = target.with_suffix(
                target.suffix + f".bak.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            )
            try:
                shutil.copy2(str(target), str(backup))
            except Exception:
                pass  # best-effort backup

        # Write
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            open_mode = "a" if mode == "append" else "w"
            with open(target, open_mode, encoding="utf-8") as f:
                f.write(content)
        except PermissionError:
            return {"ok": False, "error": "permission denied"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        return {
            "ok": True,
            "path": str(target),
            "mode": mode,
            "bytes_written": len(content.encode("utf-8")),
        }

    def dry_run(self, *, path: str = "", content: str = "", mode: str = "create", **_: Any) -> str:
        raw_path = Path(path)
        if not raw_path.is_absolute():
            target = (self._policy.workspace / raw_path).resolve()
        else:
            target = raw_path.resolve()
        ok, reason = self._policy.is_path_allowed_write(str(target))
        if not ok:
            return f"DENIED: {reason}"
        return f"Would {mode} {len(content)} chars to {target}"
