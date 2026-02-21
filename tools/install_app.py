"""
install_app — Install applications via winget / apt / flatpak.
Always requires user approval.
"""

from __future__ import annotations

import platform
import subprocess
from typing import Any

from tools.base import Tool
from policy.policy_engine import PolicyEngine


_INSTALL_CMDS = {
    "winget": ["winget", "install", "--accept-package-agreements", "--accept-source-agreements"],
    "apt":    ["sudo", "apt", "install", "-y"],
    "flatpak": ["flatpak", "install", "-y"],
}


class InstallAppTool(Tool):
    def __init__(self, policy: PolicyEngine):
        self._policy = policy

    @property
    def name(self) -> str:
        return "install_app"

    @property
    def description(self) -> str:
        return (
            "Install an application using the OS package manager "
            "(winget on Windows, apt/flatpak on Linux).  Always requires user approval."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "manager": {
                "type": "string",
                "enum": ["winget", "apt", "flatpak"],
                "description": "Package manager to use",
            },
            "package": {"type": "string", "description": "Package/app identifier"},
        }

    def run(self, *, manager: str = "", package: str = "", **_: Any) -> dict:
        if not manager or not package:
            return {"ok": False, "error": "manager and package are required"}

        ok, reason = self._policy.is_install_allowed(manager, package)
        if not ok:
            return {"ok": False, "error": reason}

        base = _INSTALL_CMDS.get(manager.lower())
        if base is None:
            return {"ok": False, "error": f"unsupported manager: {manager}"}

        cmd = base + [package]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                shell=(platform.system() == "Windows"),
            )
            return {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "installation timed out (300s)"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def dry_run(self, *, manager: str = "", package: str = "", **_: Any) -> str:
        ok, reason = self._policy.is_install_allowed(manager, package)
        if not ok:
            return f"DENIED: {reason}"
        base = _INSTALL_CMDS.get(manager.lower(), [manager])
        cmd_str = " ".join(base + [package])
        return f"Would run: {cmd_str}"
