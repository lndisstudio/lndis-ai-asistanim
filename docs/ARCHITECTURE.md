# Architecture Overview

## System Diagram

```
                       +----------------+
                       |     USER       |
                       +-------+--------+
                               |  natural language
                       +-------v--------+
                       |   CLI (REPL)   |
                       +-------+--------+
                               |
                       +-------v--------+
                       |    Agent       |
                       |  (planner +   |
                       |   executor)   |
                       +--+--------+---+
                          |        |
              +-----------v--+ +---v-----------+
              | Tool Registry| | Audit Logger  |
              +------+------+ +---------------+
                     |
            +--------v--------+
            |  Policy Engine  |  <- YAML rules
            |  (DENY-first)   |
            +--------+--------+
                     |  allow / deny / require_approval
      +------+------+-------+-------+-------+-------+
      |      |      |       |       |       |       |
   file_  file_  cmd_  install  research research  LLM
   read   write  run   _app    _local   _web    Adapter
```

## Data Flow

1. **User types a request** -> CLI passes it to `Agent.plan()`
2. **Agent uses LLM** (if available) or keyword parser to produce a `Plan`
3. **Plan is displayed** to the user (tool names, args, descriptions)
4. **User approves** via `/approve`
5. **Agent executes** each action sequentially:
   - Policy Engine evaluates the tool call
   - If DENIED -> action skipped, logged
   - If ALLOWED -> tool runs, result captured
   - Audit entry written for every action
6. **Results displayed** to the user

## Planning Modes

| Mode | When Used | How It Works |
|------|-----------|-------------|
| **LLM** | Ollama running locally, or OPENAI_API_KEY set | Agent sends request + tool schemas to LLM, gets JSON plan back |
| **Keyword** | No LLM available (fallback) | Simple prefix matching: `read`, `write`, `run`, `install`, `search`, `web` |

## LLM Integration

The `core/llm.py` module provides a unified adapter:

- **OllamaAdapter** — connects to local Ollama server (localhost:11434)
- **OpenAIAdapter** — connects to OpenAI API (requires API key)
- **FallbackAdapter** — returns helpful message when no LLM is available

Auto-detection order: Ollama -> OpenAI -> Fallback

The LLM receives:
- System prompt with security rules and output format
- Available tool schemas
- Workspace path
- User request

It responds with a JSON array of steps, which the Agent parses into Actions.

## Module Responsibilities

| Module | File | Responsibility |
|--------|------|---------------|
| Models | `core/models.py` | Shared dataclasses (Plan, Action, ToolCall, AuditEntry) |
| Agent | `core/agent.py` | Planning (LLM + keyword), approval, execution |
| LLM | `core/llm.py` | Adapter for Ollama / OpenAI / Fallback |
| Registry | `core/registry.py` | Tool registration, discovery, call routing |
| Audit | `core/audit.py` | Append-only JSONL audit trail |
| Memory | `core/memory.py` | SQLite conversation/KV store (optional) |
| CLI | `core/cli.py` | Interactive REPL with /plan, /approve, /run |
| Policy | `policy/policy_engine.py` | YAML-based deny-first rule evaluation |
| Tools | `tools/*.py` | Individual tool implementations |

## Security Layers

```
Request -> Agent -> (LLM plans) -> Registry -> Policy Engine -> Tool -> OS
                                                    |
                                              DENY? -> stop + log
                                              ALLOW? -> execute + log
                                              REQUIRE_APPROVAL? -> check flag
```

See [SECURITY.md](../SECURITY.md) for the full security model.
