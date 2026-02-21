"""
Policy Engine — the single gatekeeper for every tool call.

Loads rules from a YAML file and exposes helpers:
  is_path_allowed_read(path)
  is_path_allowed_write(path)
  is_command_allowed(cmd_parts)
  is_network_allowed()
  evaluate(tool_name, args) -> (PolicyDecision, reason)
"""

from __future__ import annotations

import os
import platform
import getpass
from pathlib import Path
from typing import Any

import yaml

from core.models import PolicyDecision


def _resolve_template(raw: str) -> str:
    """Replace {username} with the current OS user."""
    return raw.replace("{username}", getpass.getuser())


class PolicyEngine:
    """Deny-first policy evaluator."""

    def __init__(self, policy_path: str | Path | None = None):
        if policy_path is None:
            policy_path = Path(__file__).parent / "default_policy.yaml"
        self._path = Path(policy_path)
        self._cfg: dict[str, Any] = {}
        self._os = "windows" if platform.system() == "Windows" else "linux"
        self._network_override: bool | None = None  # runtime toggle
        self._load()

    # ── loading ────────────────────────────────────────────────────

    def _load(self) -> None:
        with open(self._path, "r", encoding="utf-8") as f:
            self._cfg = yaml.safe_load(f)

    def reload(self) -> None:
        self._load()

    # ── workspace ──────────────────────────────────────────────────

    @property
    def workspace(self) -> Path:
        raw = self._cfg["workspace"][self._os]
        resolved = _resolve_template(raw)
        return Path(resolved).expanduser().resolve()

    # ── protected paths ────────────────────────────────────────────

    @property
    def protected_paths(self) -> list[Path]:
        raw_list = self._cfg.get("protected_paths", {}).get(self._os, [])
        return [Path(_resolve_template(p)).expanduser().resolve() for p in raw_list]

    def _is_under_protected(self, target: Path) -> bool:
        resolved = target.resolve()
        for pp in self.protected_paths:
            try:
                resolved.relative_to(pp)
                return True
            except ValueError:
                continue
        return False

    def _is_path_traversal(self, raw: str) -> bool:
        return ".." in raw

    # ── read ───────────────────────────────────────────────────────

    def is_path_allowed_read(self, path: str) -> tuple[bool, str]:
        cfg = self._cfg.get("file_read", {})
        if not cfg.get("enabled", True):
            return False, "file_read disabled in policy"

        if self._is_path_traversal(path):
            return False, "path traversal detected (..)"

        target = Path(path).expanduser().resolve()

        # Block certain extensions
        blocked_ext = cfg.get("blocked_extensions", [])
        if target.suffix.lower() in blocked_ext:
            return False, f"extension {target.suffix} is blocked"

        # Check file size
        max_mb = cfg.get("max_size_mb", 50)
        if target.is_file() and target.stat().st_size > max_mb * 1024 * 1024:
            return False, f"file exceeds {max_mb} MB limit"

        return True, "allowed"

    # ── write ──────────────────────────────────────────────────────

    def is_path_allowed_write(self, path: str) -> tuple[bool, str]:
        cfg = self._cfg.get("file_write", {})
        if not cfg.get("enabled", True):
            return False, "file_write disabled in policy"

        if self._is_path_traversal(path):
            return False, "path traversal detected (..)"

        target = Path(path).expanduser().resolve()

        # Protected dirs
        if self._is_under_protected(target):
            return False, f"target is under a protected system directory"

        # Extension block
        blocked_ext = cfg.get("blocked_extensions", [])
        if target.suffix.lower() in blocked_ext:
            return False, f"writing {target.suffix} files is blocked"

        # Workspace-only
        if cfg.get("workspace_only", True):
            ws = self.workspace
            try:
                target.relative_to(ws)
            except ValueError:
                return False, f"writes restricted to workspace ({ws})"

        # Size check (only for existing files being overwritten)
        max_mb = cfg.get("max_size_mb", 10)
        if target.is_file() and target.stat().st_size > max_mb * 1024 * 1024:
            return False, f"file exceeds {max_mb} MB limit"

        return True, "allowed"

    # ── delete ─────────────────────────────────────────────────────

    def is_delete_allowed(self) -> tuple[bool, str]:
        if not self._cfg.get("delete", {}).get("enabled", False):
            return False, "DELETE operations are disabled by policy"
        return True, "allowed"

    # ── command ────────────────────────────────────────────────────

    def is_command_allowed(self, cmd_parts: list[str]) -> tuple[bool, str]:
        cfg = self._cfg.get("command_run", {})
        if not cfg.get("enabled", False):
            return False, "command_run disabled in policy"

        if not cmd_parts:
            return False, "empty command"

        base_cmd = Path(cmd_parts[0]).stem.lower()
        full_str = " ".join(cmd_parts)

        # Blocked characters
        for ch in cfg.get("blocked_chars", []):
            if ch in full_str:
                return False, f"blocked character '{ch}' in command"

        # Allowlist
        allowlist = [c.lower() for c in cfg.get("allowlist", [])]
        if base_cmd not in allowlist:
            return False, f"'{base_cmd}' not in command allowlist"

        return True, "allowed (requires approval)" if cfg.get("requires_approval") else "allowed"

    # ── install ────────────────────────────────────────────────────

    def is_install_allowed(self, manager: str, package: str) -> tuple[bool, str]:
        cfg = self._cfg.get("install_app", {})
        if not cfg.get("enabled", False):
            return False, "install_app disabled in policy"

        allowed = [m.lower() for m in cfg.get("allowed_managers", [])]
        if manager.lower() not in allowed:
            return False, f"package manager '{manager}' not allowed"

        blocked = [a.lower() for a in cfg.get("blocked_apps", [])]
        if package.lower() in blocked:
            return False, f"app '{package}' is blocked"

        return True, "allowed (requires approval)"

    # ── network ────────────────────────────────────────────────────

    def is_network_allowed(self) -> tuple[bool, str]:
        # Runtime toggle has priority
        if self._network_override is not None:
            if self._network_override:
                return True, "network enabled by user toggle"
            return False, "network disabled by user toggle"

        if self._cfg.get("network", {}).get("enabled", False):
            return True, "network enabled in policy"
        return False, "network disabled by default policy"

    def set_network(self, enabled: bool) -> None:
        self._network_override = enabled

    # ── generic evaluate ───────────────────────────────────────────

    def evaluate(self, tool_name: str, args: dict[str, Any]) -> tuple[PolicyDecision, str]:
        """
        High-level evaluator.  Returns (decision, reason).
        Tools should call the specific helpers; this is an extra guard.
        """
        if tool_name == "file_read":
            ok, reason = self.is_path_allowed_read(args.get("path", ""))
            return (PolicyDecision.ALLOW if ok else PolicyDecision.DENY), reason

        if tool_name == "file_write":
            # Resolve relative paths against workspace
            raw_path = args.get("path", "")
            if raw_path and not Path(raw_path).is_absolute():
                raw_path = str((self.workspace / raw_path).resolve())
            ok, reason = self.is_path_allowed_write(raw_path)
            if not ok:
                return PolicyDecision.DENY, reason
            return PolicyDecision.ALLOW, reason

        if tool_name == "command_run":
            ok, reason = self.is_command_allowed(args.get("command", []))
            if not ok:
                return PolicyDecision.DENY, reason
            if self._cfg.get("command_run", {}).get("requires_approval", True):
                return PolicyDecision.REQUIRE_APPROVAL, reason
            return PolicyDecision.ALLOW, reason

        if tool_name == "install_app":
            ok, reason = self.is_install_allowed(
                args.get("manager", ""), args.get("package", "")
            )
            if not ok:
                return PolicyDecision.DENY, reason
            return PolicyDecision.REQUIRE_APPROVAL, reason

        if tool_name == "research_web":
            ok, reason = self.is_network_allowed()
            return (PolicyDecision.ALLOW if ok else PolicyDecision.DENY), reason

        if tool_name == "research_local":
            return PolicyDecision.ALLOW, "local research is safe"

        # Unknown tool → deny
        return PolicyDecision.DENY, f"unknown tool '{tool_name}'"

    # ── info ───────────────────────────────────────────────────────

    def summary(self) -> dict:
        return {
            "os": self._os,
            "workspace": str(self.workspace),
            "network_enabled": self.is_network_allowed()[0],
            "delete_enabled": self._cfg.get("delete", {}).get("enabled", False),
            "protected_paths": [str(p) for p in self.protected_paths],
            "command_allowlist": self._cfg.get("command_run", {}).get("allowlist", []),
        }
