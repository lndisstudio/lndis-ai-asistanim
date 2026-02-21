"""
research_local — Scan workspace for txt/md/pdf, build a simple index, search.
Pure offline.  No OCR; extracts text from text-layer PDFs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.base import Tool
from policy.policy_engine import PolicyEngine


# File extensions we scan
_TEXT_EXTS = {".txt", ".md", ".csv", ".log", ".json", ".yaml", ".yml", ".ini", ".cfg", ".py", ".js", ".html", ".css"}
_PDF_EXT  = ".pdf"

# Maximum file size to index (10 MB)
_MAX_INDEX_BYTES = 10 * 1024 * 1024


class LocalResearchTool(Tool):
    def __init__(self, policy: PolicyEngine):
        self._policy = policy
        self._index: list[dict] = []       # [{path, lines}]
        self._indexed = False

    @property
    def name(self) -> str:
        return "research_local"

    @property
    def description(self) -> str:
        return (
            "Search local files in the workspace for a query.  "
            "Supports txt, md, pdf (text-layer), and common text formats.  "
            "Fully offline."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "query": {"type": "string", "description": "Search query (keywords)"},
            "scan_dir": {"type": "string", "description": "Directory to search (default: workspace)", "default": ""},
            "max_results": {"type": "integer", "description": "Max result snippets", "default": 10},
        }

    # ── indexing ───────────────────────────────────────────────────

    def _build_index(self, root: Path) -> None:
        self._index.clear()
        for fpath in root.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.stat().st_size > _MAX_INDEX_BYTES:
                continue

            ext = fpath.suffix.lower()
            lines: list[str] = []

            if ext in _TEXT_EXTS:
                lines = self._read_text(fpath)
            elif ext == _PDF_EXT:
                lines = self._read_pdf(fpath)

            if lines:
                self._index.append({"path": str(fpath), "lines": lines})

        self._indexed = True

    def _read_text(self, fpath: Path) -> list[str]:
        try:
            return fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return []

    def _read_pdf(self, fpath: Path) -> list[str]:
        """Extract text from PDF using PyMuPDF (fitz) if available."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(fpath))
            lines: list[str] = []
            for page in doc:
                text = page.get_text()
                lines.extend(text.splitlines())
            doc.close()
            return lines
        except ImportError:
            # Fallback: try pdfplumber
            try:
                import pdfplumber
                with pdfplumber.open(str(fpath)) as pdf:
                    lines = []
                    for page in pdf.pages:
                        text = page.extract_text() or ""
                        lines.extend(text.splitlines())
                    return lines
            except ImportError:
                return [f"[PDF skipped — install PyMuPDF or pdfplumber to index PDFs]"]
        except Exception:
            return []

    # ── searching ──────────────────────────────────────────────────

    def run(self, *, query: str = "", scan_dir: str = "", max_results: int = 10, **_: Any) -> dict:
        if not query.strip():
            return {"ok": False, "error": "query is required"}

        root = Path(scan_dir).expanduser().resolve() if scan_dir else self._policy.workspace
        if not root.is_dir():
            return {"ok": False, "error": f"directory not found: {root}"}

        # (Re)build index if needed
        if not self._indexed:
            self._build_index(root)

        keywords = query.lower().split()
        results: list[dict] = []

        for doc in self._index:
            for line_no, line in enumerate(doc["lines"], start=1):
                lower = line.lower()
                if all(kw in lower for kw in keywords):
                    results.append({
                        "file": doc["path"],
                        "line": line_no,
                        "snippet": line.strip()[:300],
                    })
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break

        return {
            "ok": True,
            "query": query,
            "total_files_indexed": len(self._index),
            "matches": len(results),
            "results": results,
        }

    def dry_run(self, *, query: str = "", scan_dir: str = "", **_: Any) -> str:
        root = Path(scan_dir).expanduser().resolve() if scan_dir else self._policy.workspace
        return f"Would search '{query}' in {root} (offline keyword scan)"
