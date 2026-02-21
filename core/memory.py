"""
Simple SQLite-backed memory for conversation / context storage (optional).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "memory.db"


class Memory:
    """Lightweight key-value + conversation store."""

    def __init__(self, db_path: str | Path | None = None):
        self._path = Path(db_path) if db_path else _DEFAULT_DB
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id   TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS kv (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        self._conn.commit()

    # ── conversation ───────────────────────────────────────────────

    def add_message(self, role: str, content: str) -> str:
        msg_id = uuid.uuid4().hex[:12]
        self._conn.execute(
            "INSERT INTO conversations (id, role, content, ts) VALUES (?,?,?,?)",
            (msg_id, role, content, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return msg_id

    def get_history(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT role, content, ts FROM conversations ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"role": r, "content": c, "ts": t} for r, c, t in reversed(rows)]

    # ── key-value ──────────────────────────────────────────────────

    def set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO kv (key, value) VALUES (?,?)", (key, value)
        )
        self._conn.commit()

    def get(self, key: str, default: str = "") -> str:
        row = self._conn.execute(
            "SELECT value FROM kv WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else default

    def close(self) -> None:
        self._conn.close()
