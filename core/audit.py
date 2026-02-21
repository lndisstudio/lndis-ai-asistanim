"""
Structured Audit Logger — records every tool invocation to a JSON-lines file.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.models import AuditEntry
from core.settings import _get_default_settings_dir

_DEFAULT_LOG_DIR = _get_default_settings_dir()


class AuditLogger:
    """Append-only audit trail stored as newline-delimited JSON."""

    def __init__(self, log_dir: str | Path | None = None):
        self._dir = Path(log_dir) if log_dir else _DEFAULT_LOG_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "audit.jsonl"
        self._entries: list[AuditEntry] = []

    # ── write ──────────────────────────────────────────────────────

    def log(
        self,
        tool_name: str,
        args: dict[str, Any],
        policy_decision: str,
        policy_reason: str,
        result: str = "",
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            tool_name=tool_name,
            args=args,
            policy_decision=policy_decision,
            policy_reason=policy_reason,
            result=result,
            error=error,
            duration_ms=duration_ms,
        )
        self._entries.append(entry)
        self._persist(entry)
        return entry

    def _persist(self, entry: AuditEntry) -> None:
        with open(self._file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    # ── read ───────────────────────────────────────────────────────

    def recent(self, n: int = 20) -> list[AuditEntry]:
        """Return the last *n* entries (from memory)."""
        return list(reversed(self._entries[-n:]))

    def load_from_disk(self) -> list[dict]:
        """Read all entries from the JSONL file."""
        if not self._file.exists():
            return []
        entries = []
        with open(self._file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def count(self) -> int:
        return len(self._entries)
