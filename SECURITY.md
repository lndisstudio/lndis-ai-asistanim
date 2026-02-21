# Lndis AI Assistant — Security Model

## Core Principles

| # | Principle | Enforcement |
|---|-----------|------------|
| 1 | **LLM has ZERO direct system access** | All actions routed through Tools → Policy Engine |
| 2 | **Deny by default** | Policy Engine denies anything not explicitly allowed |
| 3 | **No delete operations** | `delete.enabled: false` in policy — cannot delete files, uninstall apps, or remove directories |
| 4 | **Workspace-only writes** | `file_write.workspace_only: true` — writes restricted to `~/lndis-workspace/` |
| 5 | **Network off by default** | `network.enabled: false` — user must explicitly toggle on |
| 6 | **Plan → Approve → Execute** | User sees the plan before anything runs |
| 7 | **Full audit trail** | Every tool call logged to `data/audit.jsonl` with timestamp, args, decision, result |

## Protected System Directories

These paths are **never writable**, regardless of any other setting:

### Windows
- `C:\Windows`
- `C:\Program Files`
- `C:\Program Files (x86)`
- `C:\ProgramData`
- `C:\Users\{user}\AppData`
- `C:\$Recycle.Bin`

### Linux
- `/bin`, `/sbin`, `/usr`, `/etc`, `/var`, `/boot`, `/root`, `/`

## Command Execution

Commands are gated by a strict allowlist defined in `policy/default_policy.yaml`.

**Allowed:** `dir`, `ls`, `cat`, `type`, `find`, `grep`, `whoami`, `hostname`, `python`, `pip`, `node`, `npm`, `code`, `notepad`, etc.

**Blocked characters** (prevent injection): `>`, `>>`, `|`, `&&`, `||`, `;`, `` ` ``, `$(`

**Every command requires explicit user approval.**

## Application Installation

- Only via approved package managers: `winget`, `apt`, `flatpak`
- Always requires user approval
- Specific apps can be blocklisted in policy

## Network Access

- **Default: disabled**
- User toggles on/off per session via CLI (`/network on`)
- When off, `research_web` tool returns "network disabled"
- No background network activity ever

## Audit Logging

Every tool invocation produces an immutable audit entry:

```json
{
  "id": "a1b2c3d4e5f6",
  "timestamp": "2026-02-21T13:00:00Z",
  "tool_name": "file_write",
  "args": {"path": "notes.txt", "content": "..."},
  "policy_decision": "allow",
  "policy_reason": "allowed",
  "result": "ok",
  "duration_ms": 12
}
```

Logs are stored in `data/audit.jsonl` and can be queried via `/logs` in the CLI.

## Threat Model

| Threat | Mitigation |
|--------|-----------|
| Prompt injection tries to delete files | DELETE disabled at policy level — no tool exists to delete |
| LLM tries to write to system dirs | Path validation blocks all protected directories |
| LLM tries shell injection via `>`, `|` | Blocked characters list in command policy |
| LLM tries to run `rm`, `del`, `format` | Not in command allowlist → denied |
| LLM tries to access internet | Network disabled by default; hard toggle |
| LLM tries to call unknown tool | `evaluate()` returns DENY for unknown tools |
| Path traversal (`../../etc/passwd`) | `..` detection in all path validators |
