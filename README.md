# Lndis AI Asistanı (LNDIS AI Assistant)

> Local-first, security-first desktop AI assistant.  
> Default offline. No remote access. Policy-gated tools.

## Quick Start

```bash
# 1. Clone
git clone <repo-url>
cd Lndis-Ai-Asistani

# 2. Install dependencies
pip install pyyaml pytest

# 3. (Optional) LLM setup — choose one:
#    Local (recommended):
#      Install Ollama: https://ollama.ai
#      ollama pull llama3.2
#    Cloud:
#      set OPENAI_API_KEY=sk-...

# 4. (Optional) extras:
pip install PyMuPDF            # PDF research
pip install duckduckgo_search  # Web research

# 5. Run the CLI
python -m core.cli
```

## CLI Commands

| Command | Action |
|---------|--------|
| `/plan <request>` | Generate a plan from natural language |
| `/approve` | Approve the current plan |
| `/run` | Execute the approved plan |
| `/logs [n]` | Show last *n* audit entries (default 10) |
| `/tools` | List available tools |
| `/model` | Show LLM adapter info |
| `/network on\|off` | Toggle network access |
| `/status` | Show policy summary |
| `/help` | Show help |
| `/quit` | Exit |

You can also type a request directly (same as `/plan <request>`).

## Example Session

```
lndis> /plan read C:\Users\me\lndis-workspace\notes.txt

═══ PLAN ═══════════════════════════════════════
  ID: a1b2c3d4e5f6
  Request: read C:\Users\me\lndis-workspace\notes.txt
  Summary: Read C:\Users\me\lndis-workspace\notes.txt

  Step 1: Read C:\Users\me\lndis-workspace\notes.txt
          tool=file_read  args={'path': '...\\notes.txt'}

  → /approve to approve, then /run to execute.
════════════════════════════════════════════════

lndis> /approve
  ✓ Plan approved.  Use /run to execute.

lndis> /run
═══ RESULTS ════════════════════════════════════
  ✓  Step 1: Read notes.txt
        File: C:\Users\me\lndis-workspace\notes.txt (3 lines)
        │ Hello world
        │ This is a test
        │ Line three
════════════════════════════════════════════════
```

## Security Model

See [SECURITY.md](SECURITY.md) for the full security documentation.

**Summary of non-negotiable rules:**

1. ❌ LLM has **zero** direct system access — all actions via Tools
2. ❌ **DELETE** operations disabled (no file delete, no uninstall)
3. ❌ Writes **only** inside `~/lndis-workspace/`
4. ❌ Network **off** by default
5. ❌ Protected system directories **never writable**
6. ✅ Every action goes through: **Plan → Approve → Execute → Audit**
7. ✅ Full audit trail in `data/audit.jsonl`

## Project Structure

```
├── core/
│   ├── agent.py          # Planner + executor (LLM + keyword)
│   ├── llm.py            # LLM adapter (Ollama / OpenAI / Fallback)
│   ├── models.py         # Dataclasses (Plan, Action, ToolCall)
│   ├── registry.py       # Tool registry
│   ├── audit.py          # JSONL audit logger
│   ├── memory.py         # SQLite store (optional)
│   └── cli.py            # Interactive CLI
├── policy/
│   ├── policy_engine.py  # Deny-first policy evaluator
│   └── default_policy.yaml
├── tools/
│   ├── base.py           # Tool interface
│   ├── file_read.py      # Read files / list dirs
│   ├── file_write.py     # Write files (workspace only)
│   ├── command_run.py    # Run commands (allowlist + approval)
│   ├── install_app.py    # Install apps (winget/apt/flatpak)
│   ├── research_local.py # Offline local search
│   └── research_web.py   # Web search (network toggle)
├── tests/
│   └── test_policy.py    # Policy security tests
├── docs/
│   └── architecture.md   # System architecture
├── SECURITY.md           # Security model
└── README.md             # This file
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Roadmap

| Phase | Status | Content |
|-------|--------|---------|
| **1 - MVP** | Done | Policy engine, tools, plan/approve/run, CLI, audit |
| **2 - LLM** | Done | Ollama/OpenAI integration, smart planning, dual-mode |
| **3 - Voice** | Planned | whisper.cpp STT + Piper TTS |
| **4 - UI** | Planned | Tauri or Electron desktop app |
| **5 - Advanced** | Planned | RAG, app automation, plugins |

## License

All rights reserved. © 2026 Lndis
