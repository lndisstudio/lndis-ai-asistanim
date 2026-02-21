"""
LLM Adapter — unified interface for multiple providers.

Supported providers:
  - ollama     (local, offline, no API key needed)
  - deepseek   (OpenAI-compatible, https://api.deepseek.com)
  - openai     (https://api.openai.com/v1)
  - groq       (https://api.groq.com/openai/v1)
  - openrouter (https://openrouter.ai/api/v1)

Auto-detection priority: Ollama -> DeepSeek/OpenAI (if API key set) -> Fallback

Usage:
    from core.settings import Settings
    settings = Settings()
    adapter = LLMAdapter.from_settings(settings)
    response = adapter.chat(messages)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.settings import Settings


# -- Response dataclass -----------------------------------------------------

@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    usage: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


# -- Base class -------------------------------------------------------------

class LLMAdapter:
    """Abstract LLM adapter."""

    provider_name: str = "unknown"

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError

    @staticmethod
    def from_settings(settings: "Settings") -> LLMAdapter:
        """Create adapter from persistent settings."""
        cfg = settings.raw()
        provider = cfg.get("provider", "auto")
        api_key = cfg.get("api_key", "")
        model = cfg.get("model", "")
        base_url = cfg.get("base_url", "")

        if provider == "auto":
            # 1. Try Ollama (local)
            ollama = OllamaAdapter(model=model or "llama3.2")
            if ollama.is_available():
                return ollama
            # 2. Try configured API key with deepseek/openai
            if api_key:
                url = base_url or "https://api.deepseek.com"
                mdl = model or "deepseek-chat"
                return OpenAICompatAdapter(
                    model=mdl, api_key=api_key, base_url=url,
                    provider_label="deepseek" if "deepseek" in url else "openai",
                )
            # 3. Try env var
            env_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
            if env_key:
                return OpenAICompatAdapter(
                    model=model or "deepseek-chat",
                    api_key=env_key,
                    base_url=base_url or "https://api.deepseek.com",
                    provider_label="env",
                )
            return FallbackAdapter()

        if provider == "ollama":
            return OllamaAdapter(
                model=model or "llama3.2",
                base_url=base_url or "http://localhost:11434",
            )

        # All other providers use OpenAI-compatible API
        if not api_key:
            # Try env vars as fallback
            api_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            return FallbackAdapter()

        from core.settings import PROVIDER_PRESETS
        preset = PROVIDER_PRESETS.get(provider, {})
        return OpenAICompatAdapter(
            model=model or preset.get("model", "deepseek-chat"),
            api_key=api_key,
            base_url=base_url or preset.get("base_url", "https://api.deepseek.com"),
            provider_label=provider,
        )

    @staticmethod
    def create(provider: str = "auto", **kwargs: Any) -> LLMAdapter:
        """Legacy factory (env-based, no settings file)."""
        if provider == "auto":
            ollama = OllamaAdapter(**kwargs)
            if ollama.is_available():
                return ollama
            env_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
            if env_key:
                return OpenAICompatAdapter(api_key=env_key, **kwargs)
            return FallbackAdapter()
        if provider == "ollama":
            return OllamaAdapter(**kwargs)
        return OpenAICompatAdapter(provider_label=provider, **kwargs)


# -- Ollama (local) ---------------------------------------------------------

class OllamaAdapter(LLMAdapter):
    """Connects to a local Ollama server."""

    provider_name = "ollama"

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434", **_: Any):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = self._format_tools(tools)

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return LLMResponse(content=f"[Ollama error: {exc}]", model=self.model, provider="ollama")

        msg = body.get("message", {})
        return LLMResponse(
            content=msg.get("content", ""),
            tool_calls=self._parse_tool_calls(msg),
            model=self.model,
            provider="ollama",
            usage={"prompt_tokens": body.get("prompt_eval_count", 0), "completion_tokens": body.get("eval_count", 0)},
            raw=body,
        )

    def _format_tools(self, tools: list[dict]) -> list[dict]:
        formatted = []
        for t in tools:
            props, req_list = {}, []
            for pname, pinfo in t.get("input_schema", {}).items():
                props[pname] = {"type": pinfo.get("type", "string"), "description": pinfo.get("description", "")}
                if "default" not in pinfo:
                    req_list.append(pname)
            formatted.append({
                "type": "function",
                "function": {"name": t["name"], "description": t["description"],
                             "parameters": {"type": "object", "properties": props, "required": req_list}},
            })
        return formatted

    def _parse_tool_calls(self, msg: dict) -> list[dict]:
        return [{"name": c.get("function", {}).get("name", ""),
                 "args": c.get("function", {}).get("arguments", {})}
                for c in msg.get("tool_calls", [])]


# -- OpenAI-compatible (DeepSeek, OpenAI, Groq, OpenRouter) -----------------

class OpenAICompatAdapter(LLMAdapter):
    """Works with any OpenAI-compatible API (DeepSeek, OpenAI, Groq, etc.)."""

    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: str = "",
        base_url: str = "https://api.deepseek.com",
        provider_label: str = "deepseek",
        **_: Any,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.provider_name = provider_label

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        # Build the endpoint URL
        url = f"{self.base_url}/chat/completions"
        # Some providers already have /v1 in the base_url
        if not self.base_url.endswith("/v1") and "/v1/" not in self.base_url:
            url = f"{self.base_url}/v1/chat/completions"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = self._format_tools(tools)

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            return LLMResponse(
                content=f"[{self.provider_name} API error {exc.code}: {error_body}]",
                model=self.model,
                provider=self.provider_name,
            )
        except urllib.error.URLError as exc:
            return LLMResponse(
                content=f"[{self.provider_name} connection error: {exc}]",
                model=self.model,
                provider=self.provider_name,
            )

        choice = body.get("choices", [{}])[0]
        msg = choice.get("message", {})

        return LLMResponse(
            content=msg.get("content", "") or "",
            tool_calls=self._parse_tool_calls(msg),
            model=body.get("model", self.model),
            provider=self.provider_name,
            usage=body.get("usage", {}),
            raw=body,
        )

    def _format_tools(self, tools: list[dict]) -> list[dict]:
        formatted = []
        for t in tools:
            props, req_list = {}, []
            for pname, pinfo in t.get("input_schema", {}).items():
                props[pname] = {"type": pinfo.get("type", "string"), "description": pinfo.get("description", "")}
                if "default" not in pinfo:
                    req_list.append(pname)
            formatted.append({
                "type": "function",
                "function": {"name": t["name"], "description": t["description"],
                             "parameters": {"type": "object", "properties": props, "required": req_list}},
            })
        return formatted

    def _parse_tool_calls(self, msg: dict) -> list[dict]:
        calls = msg.get("tool_calls", [])
        parsed = []
        for call in calls:
            fn = call.get("function", {})
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            parsed.append({"name": fn.get("name", ""), "args": args})
        return parsed


# -- Fallback (no LLM) -----------------------------------------------------

class FallbackAdapter(LLMAdapter):
    """Used when no LLM is available."""

    provider_name = "none"

    def __init__(self):
        self.model = "none"

    def is_available(self) -> bool:
        return True  # always "available" as fallback

    def chat(self, messages: list[dict[str, str]], **_: Any) -> LLMResponse:
        return LLMResponse(
            content=(
                "No LLM configured. Use /set provider deepseek and "
                "/set api_key <YOUR_KEY> to configure, or install Ollama "
                "for local AI."
            ),
            model="none",
            provider="none",
        )
