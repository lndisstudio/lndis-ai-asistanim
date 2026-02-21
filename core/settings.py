"""
Settings Manager — persistent configuration stored as JSON.

Stored in data/settings.json.  Survives across sessions.
Settings include: LLM provider, API key, model name, etc.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _get_default_settings_dir() -> Path:
    """
    Get persistent data dir — priority order:
    1. Installed app:  C:\\Program Files\\Lndis AI\\data
    2. Packaged .exe:  %LOCALAPPDATA%\\LndisAI
    3. Dev mode:       project/data
    """
    # Check if installed to Program Files
    pf_dir = Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Lndis AI" / "data"
    if pf_dir.parent.exists():
        pf_dir.mkdir(parents=True, exist_ok=True)
        return pf_dir

    if getattr(sys, 'frozen', False):
        # Running as portable .exe — use AppData
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LndisAI"
    else:
        # Running as script — use project/data
        base = Path(__file__).resolve().parent.parent / "data"
    return base

_DEFAULT_SETTINGS_DIR = _get_default_settings_dir()

# Provider presets: {provider: {base_url, default_model}}
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "ollama":   {"base_url": "http://localhost:11434",     "model": "llama3.2"},
    "deepseek": {"base_url": "https://api.deepseek.com",   "model": "deepseek-chat"},
    "openai":   {"base_url": "https://api.openai.com/v1",  "model": "gpt-4o-mini"},
    "groq":     {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.1-70b-versatile"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "deepseek/deepseek-chat"},
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "provider": "auto",
    "api_key": "",
    "model": "",
    "base_url": "",
    "temperature": 0.3,
    "max_tokens": 2048,
    "network_enabled": False,
}


class Settings:
    """Read/write persistent settings."""

    def __init__(self, settings_dir: str | Path | None = None):
        self._dir = Path(settings_dir) if settings_dir else _DEFAULT_SETTINGS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "settings.json"
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._data = json.loads(f.read())
            except (json.JSONDecodeError, OSError):
                self._data = {}
        # Merge defaults for any missing keys
        for k, v in DEFAULT_SETTINGS.items():
            self._data.setdefault(k, v)

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # -- access -------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def all(self) -> dict[str, Any]:
        """Return all settings (masks API key for display)."""
        out = dict(self._data)
        if out.get("api_key"):
            key = out["api_key"]
            out["api_key"] = key[:8] + "..." + key[-4:] if len(key) > 12 else "****"
        return out

    def raw(self) -> dict[str, Any]:
        """Return all settings including full API key (for internal use)."""
        return dict(self._data)

    # -- provider helpers ---------------------------------------------------

    def set_provider(self, provider: str) -> str:
        """Set provider and apply preset defaults.  Returns info message."""
        provider = provider.lower().strip()
        preset = PROVIDER_PRESETS.get(provider)

        self.set("provider", provider)

        if preset:
            # Apply preset base_url and model if not already custom-set
            if not self._data.get("base_url") or self._data.get("provider") != provider:
                self.set("base_url", preset["base_url"])
            if not self._data.get("model") or self._data.get("provider") != provider:
                self.set("model", preset["model"])
            return f"Provider set to '{provider}' (url={preset['base_url']}, model={preset['model']})"
        else:
            return f"Provider set to '{provider}' (custom — set base_url and model manually)"

    def set_api_key(self, key: str) -> str:
        """Set API key.  Returns masked confirmation."""
        self.set("api_key", key.strip())
        masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "****"
        return f"API key saved: {masked}"

    @property
    def is_configured(self) -> bool:
        """Check if enough settings exist to create an LLM adapter."""
        provider = self._data.get("provider", "auto")
        if provider == "ollama":
            return True  # doesn't need API key
        if provider == "auto":
            return True  # will try available options
        return bool(self._data.get("api_key"))

    @staticmethod
    def list_providers() -> list[str]:
        return list(PROVIDER_PRESETS.keys())
