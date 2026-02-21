"""
Interactive CLI for Lndis AI Assistant.

Run with:  python -m core.cli

Commands:
  /plan <request>   - generate a plan from natural language
  /approve          - approve the current plan
  /run              - execute the approved plan
  /logs [n]         - show last n audit entries
  /tools            - list available tools
  /set <key> <val>  - configure settings (provider, api_key, model, etc.)
  /config           - show all settings
  /model            - show LLM adapter info
  /network on|off   - toggle network access
  /status           - show policy summary
  /help             - show this help
  /quit             - exit

You can also type a request directly (same as /plan <request>).
"""

from __future__ import annotations

import io
import json
import os
import sys
import textwrap

# Force UTF-8 on Windows console
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")

from core.agent import Agent
from core.models import ActionStatus, Plan
from core.settings import Settings, PROVIDER_PRESETS


# -- ANSI helpers -----------------------------------------------------------

_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_RED   = "\033[91m"
_GREEN = "\033[92m"
_YELLOW= "\033[93m"
_CYAN  = "\033[96m"
_ORANGE= "\033[38;5;214m"
_BLUE  = "\033[94m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{_RESET}"


def _print(text: str = "") -> None:
    """Safe print that handles encoding errors gracefully."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


# -- display helpers --------------------------------------------------------

def show_plan(plan: Plan) -> None:
    _print()
    _print(_c("=== PLAN =======================================", _ORANGE))
    _print(f"  {_c('ID:', _DIM)} {plan.id}")
    _print(f"  {_c('Request:', _DIM)} {plan.user_request}")
    _print(f"  {_c('Summary:', _DIM)} {plan.summary}")
    _print()
    for i, action in enumerate(plan.actions, 1):
        tc = action.tool_call
        _print(f"  {_c(f'Step {i}:', _CYAN)} {action.description}")
        _print(f"          tool={_c(tc.tool_name, _YELLOW)}  args={tc.args}")
    _print()
    _print(f"  {_c('-> /approve', _GREEN)} to approve, then {_c('/run', _GREEN)} to execute.")
    _print(_c("================================================", _ORANGE))
    _print()


def show_results(plan: Plan) -> None:
    _print()
    _print(_c("=== RESULTS ====================================", _ORANGE))
    for i, action in enumerate(plan.actions, 1):
        if action.status == ActionStatus.COMPLETED:
            icon = _c("[OK]", _GREEN)
        elif action.status == ActionStatus.DENIED:
            icon = _c("[DENIED]", _RED)
        elif action.status == ActionStatus.FAILED:
            icon = _c("[FAIL]", _RED)
        else:
            icon = _c("[?]", _YELLOW)

        _print(f"  {icon}  Step {i}: {action.description}")
        if action.error:
            _print(f"        {_c('Error:', _RED)} {action.error}")
        elif action.result:
            result = action.result
            if isinstance(result, dict):
                if result.get("type") == "directory":
                    entries = result.get("entries", [])
                    _print(f"        Directory: {result.get('path')} ({len(entries)} items)")
                    for e in entries[:15]:
                        kind = "[D]" if e["type"] == "dir" else "[F]"
                        _print(f"          {kind} {e['name']}")
                    if len(entries) > 15:
                        _print(f"          ... and {len(entries)-15} more")
                elif result.get("type") == "file":
                    content = result.get("content", "")
                    lines = content.split("\n")
                    _print(f"        File: {result.get('path')} ({result.get('lines')} lines)")
                    for ln in lines[:20]:
                        _print(f"        | {ln}")
                    if len(lines) > 20:
                        _print(f"        | ... ({len(lines)-20} more lines)")
                elif "stdout" in result:
                    stdout = result["stdout"].strip()
                    if stdout:
                        for ln in stdout.split("\n")[:20]:
                            _print(f"        | {ln}")
                elif "results" in result:
                    for r in result["results"][:10]:
                        if "snippet" in r and "file" in r:
                            _print(f"        >> {r['file']}:{r.get('line','')}  {r['snippet'][:80]}")
                        elif "title" in r:
                            _print(f"        [web] {r['title']}")
                            _print(f"              {r.get('url','')}")
                else:
                    display = json.dumps(result, ensure_ascii=True, indent=2)
                    for ln in display.split("\n")[:15]:
                        _print(f"        {ln}")
            else:
                _print(f"        {str(result)[:200]}")
    _print(_c("================================================", _ORANGE))
    _print()


def show_logs(agent: Agent, n: int) -> None:
    entries = agent.audit.recent(n)
    if not entries:
        _print(_c("  (no audit entries yet)", _DIM))
        return
    _print()
    _print(_c("=== AUDIT LOG ==================================", _ORANGE))
    for e in entries:
        ts = e.timestamp.strftime("%H:%M:%S")
        dec = _c(e.policy_decision, _GREEN if "allow" in e.policy_decision else _RED)
        err = f"  err={e.error}" if e.error else ""
        ms = f"  {e.duration_ms}ms" if e.duration_ms else ""
        _print(f"  {_c(ts, _DIM)}  {dec}  {_c(e.tool_name, _CYAN)}{ms}{err}")
    _print(_c("================================================", _ORANGE))
    _print()


def show_settings(settings: Settings) -> None:
    """Display all persistent settings."""
    _print()
    _print(_c("=== SETTINGS ===================================", _ORANGE))
    for k, v in settings.all().items():
        _print(f"  {_c(k, _CYAN):30s} {v}")
    _print()
    _print(f"  {_c('Supported providers:', _DIM)} {', '.join(Settings.list_providers())}")
    _print(_c("================================================", _ORANGE))
    _print()


def show_setup_guide() -> None:
    """Show first-run setup guide when no LLM is configured."""
    _print()
    _print(_c("=== QUICK SETUP ================================", _BLUE))
    _print(f"  No AI provider configured yet.  Set one up:")
    _print()
    _print(f"  {_c('DeepSeek (recommended):', _BOLD)}")
    _print(f"    /set provider deepseek")
    _print(f"    /set api_key sk-XXXXXXXXXXXXXXXXXXXX")
    _print()
    _print(f"  {_c('OpenAI:', _BOLD)}")
    _print(f"    /set provider openai")
    _print(f"    /set api_key sk-XXXXXXXXXXXXXXXXXXXX")
    _print()
    _print(f"  {_c('Ollama (local, free):', _BOLD)}")
    _print(f"    Install from https://ollama.ai")
    _print(f"    ollama pull llama3.2")
    _print(f"    /set provider ollama")
    _print()
    _print(f"  {_c('Groq (fast, free tier):', _BOLD)}")
    _print(f"    /set provider groq")
    _print(f"    /set api_key gsk_XXXXXXXXXXXXXXXXXXXX")
    _print()
    _print(f"  After setup, type a request to test:")
    _print(f"    {_c('run whoami', _GREEN)}")
    _print(_c("================================================", _BLUE))
    _print()


# -- REPL -------------------------------------------------------------------

def _banner(agent: Agent) -> str:
    mode = _c(agent.planning_mode.upper(), _GREEN if agent.planning_mode == "llm" else _YELLOW)
    model_info = ""
    if hasattr(agent.llm, "model") and agent.llm.model != "none":
        provider_label = getattr(agent.llm, "provider_name", "")
        model_info = f" ({provider_label}/{agent.llm.model})" if provider_label else f" ({agent.llm.model})"
    return (
        f"\n{_c('+----------------------------------------------+', _ORANGE)}\n"
        f"{_c('|', _ORANGE)}  {_c('Lndis AI Assistant', _BOLD)}  {_c('v0.2.0', _DIM)}                  {_c('|', _ORANGE)}\n"
        f"{_c('|', _ORANGE)}  {_c('Security-first  Local-first  Offline', _DIM)}      {_c('|', _ORANGE)}\n"
        f"{_c('+----------------------------------------------+', _ORANGE)}\n"
        f"  Planning: {mode}{model_info}\n"
        f"  Workspace: {{workspace}}\n"
        f"  Type {_c('/help', _GREEN)} for commands.  {_c('/quit', _RED)} to exit.\n"
    )


def handle_set(agent: Agent, parts: list[str]) -> None:
    """Handle /set key value commands."""
    if len(parts) < 2:
        _print(_c("  Usage: /set <key> <value>", _YELLOW))
        _print(_c("  Keys:  provider, api_key, model, base_url, temperature, max_tokens", _DIM))
        _print(f"  Providers: {', '.join(Settings.list_providers())}")
        return

    key = parts[1].lower()
    value = " ".join(parts[2:]) if len(parts) > 2 else ""

    if key == "provider":
        if not value:
            _print(_c("  Usage: /set provider <name>", _YELLOW))
            _print(f"  Options: {', '.join(Settings.list_providers())}")
            return
        msg = agent.settings.set_provider(value)
        _print(_c(f"  [+] {msg}", _GREEN))
        agent.reload_llm()
        _print(f"  Planning mode: {_c(agent.planning_mode.upper(), _GREEN if agent.planning_mode == 'llm' else _YELLOW)}")

    elif key in ("api_key", "apikey", "key"):
        if not value:
            _print(_c("  Usage: /set api_key <your-api-key>", _YELLOW))
            return
        msg = agent.settings.set_api_key(value)
        _print(_c(f"  [+] {msg}", _GREEN))
        agent.reload_llm()
        mode = agent.planning_mode
        _print(f"  Planning mode: {_c(mode.upper(), _GREEN if mode == 'llm' else _YELLOW)}")
        if mode == "llm":
            _print(_c("  AI is ready! Type a request to start.", _GREEN))

    elif key == "model":
        if not value:
            _print(_c("  Usage: /set model <model-name>", _YELLOW))
            _print(f"  Examples: deepseek-chat, deepseek-reasoner, gpt-4o-mini, llama3.2")
            return
        agent.settings.set("model", value)
        agent.reload_llm()
        _print(_c(f"  [+] Model set to: {value}", _GREEN))

    elif key in ("base_url", "url", "endpoint"):
        if not value:
            _print(_c("  Usage: /set base_url <url>", _YELLOW))
            return
        agent.settings.set("base_url", value)
        agent.reload_llm()
        _print(_c(f"  [+] Base URL set to: {value}", _GREEN))

    elif key == "temperature":
        try:
            temp = float(value)
            agent.settings.set("temperature", temp)
            _print(_c(f"  [+] Temperature set to: {temp}", _GREEN))
        except ValueError:
            _print(_c("  Temperature must be a number (0.0 - 2.0)", _RED))

    elif key == "max_tokens":
        try:
            mt = int(value)
            agent.settings.set("max_tokens", mt)
            _print(_c(f"  [+] Max tokens set to: {mt}", _GREEN))
        except ValueError:
            _print(_c("  max_tokens must be an integer", _RED))

    else:
        _print(_c(f"  Unknown setting: {key}", _RED))
        _print(_c("  Keys: provider, api_key, model, base_url, temperature, max_tokens", _DIM))


def main() -> None:
    settings = Settings()
    agent = Agent(settings=settings)

    _print(_banner(agent).replace("{workspace}", str(agent.policy.workspace)))

    # Show setup guide on first run (no API configured)
    if agent.planning_mode == "keyword":
        show_setup_guide()

    while True:
        try:
            raw = input(_c("lndis> ", _ORANGE)).strip().lstrip("\ufeff")
        except (EOFError, KeyboardInterrupt):
            _print("\nBye!")
            break

        if not raw:
            continue

        # -- /quit --
        if raw.lower() in ("/quit", "/exit", "/q"):
            _print("Bye!")
            break

        # -- /help --
        if raw.lower() in ("/help", "/h", "/?"):
            _print(textwrap.dedent("""
              /plan <request>   Plan an action
              /approve          Approve current plan
              /run              Execute approved plan
              /logs [n]         Show audit log (default 10)
              /tools            List available tools
              /set <key> <val>  Configure settings
              /config           Show all settings
              /model            Show LLM adapter info
              /network on|off   Toggle network
              /status           Policy summary
              /quit             Exit

              Setting keys:
                provider   - ollama, deepseek, openai, groq, openrouter
                api_key    - your API key
                model      - model name (deepseek-chat, gpt-4o-mini, etc.)
                base_url   - custom API endpoint
            """))
            continue

        # -- /tools --
        if raw.lower() in ("/tools", "/araclar"):
            tools = agent.list_tools()
            _print()
            for t in tools:
                _print(f"  {_c(t['name'], _CYAN):30s} {t['description']}")
            _print()
            continue

        # -- /set --
        if raw.lower().startswith("/set"):
            parts = raw.split()
            handle_set(agent, parts)
            continue

        # -- /config --
        if raw.lower() in ("/config", "/settings", "/ayarlar"):
            show_settings(agent.settings)
            continue

        # -- /model --
        if raw.lower() in ("/model", "/llm"):
            _print()
            _print(f"  {_c('planning_mode', _CYAN):30s} {agent.planning_mode}")
            _print(f"  {_c('adapter', _CYAN):30s} {type(agent.llm).__name__}")
            _print(f"  {_c('provider', _CYAN):30s} {getattr(agent.llm, 'provider_name', 'unknown')}")
            if hasattr(agent.llm, 'model'):
                _print(f"  {_c('model', _CYAN):30s} {agent.llm.model}")
            if hasattr(agent.llm, 'base_url'):
                _print(f"  {_c('endpoint', _CYAN):30s} {agent.llm.base_url}")
            _print(f"  {_c('available', _CYAN):30s} {agent.llm.is_available()}")
            _print()
            continue

        # -- /status --
        if raw.lower() == "/status":
            s = agent.policy.summary()
            _print()
            _print(f"  {_c('planning_mode', _CYAN):30s} {agent.planning_mode}")
            _print(f"  {_c('provider', _CYAN):30s} {getattr(agent.llm, 'provider_name', 'unknown')}")
            for k, v in s.items():
                _print(f"  {_c(k, _CYAN):30s} {v}")
            _print(f"  {_c('audit_entries', _CYAN):30s} {agent.audit.count()}")
            _print()
            continue

        # -- /network --
        if raw.lower().startswith("/network"):
            parts = raw.split()
            if len(parts) >= 2 and parts[1].lower() in ("on", "true", "1"):
                agent.policy.set_network(True)
                _print(_c("  [+] Network ENABLED for this session.", _GREEN))
            else:
                agent.policy.set_network(False)
                _print(_c("  [-] Network DISABLED.", _YELLOW))
            continue

        # -- /logs --
        if raw.lower().startswith("/logs"):
            parts = raw.split()
            n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
            show_logs(agent, n)
            continue

        # -- /approve --
        if raw.lower() == "/approve":
            if agent.current_plan is None:
                _print(_c("  No active plan.  Use /plan <request> first.", _YELLOW))
            elif agent.current_plan.approved:
                _print(_c("  Plan already approved.  Use /run to execute.", _DIM))
            else:
                agent.approve()
                _print(_c("  [+] Plan approved.  Use /run to execute.", _GREEN))
            continue

        # -- /run --
        if raw.lower() == "/run":
            if agent.current_plan is None:
                _print(_c("  No active plan.", _YELLOW))
            elif not agent.current_plan.approved:
                _print(_c("  Plan not approved.  Use /approve first.", _YELLOW))
            else:
                plan = agent.execute()
                show_results(plan)
            continue

        # -- /plan <request> or bare request --
        request = raw
        if raw.lower().startswith("/plan "):
            request = raw[6:].strip()

        if not request:
            continue

        plan = agent.plan(request)
        show_plan(plan)


if __name__ == "__main__":
    main()
