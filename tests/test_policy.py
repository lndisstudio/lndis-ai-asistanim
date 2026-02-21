"""
Policy Engine tests — verifying the non-negotiable security rules.
Run with:  python -m pytest tests/test_policy.py -v
"""

import platform
import pytest
from pathlib import Path

from policy.policy_engine import PolicyEngine


@pytest.fixture
def policy():
    """Load the default policy."""
    return PolicyEngine()


# ── DELETE is always denied ────────────────────────────────────────

class TestDeleteDenied:
    def test_delete_disabled(self, policy):
        ok, reason = policy.is_delete_allowed()
        assert ok is False
        assert "disabled" in reason.lower()


# ── Protected system paths ─────────────────────────────────────────

class TestProtectedPaths:
    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only")
    @pytest.mark.parametrize("path", [
        r"C:\Windows\system32\config.sys",
        r"C:\Program Files\test.txt",
        r"C:\Program Files (x86)\app\data.log",
        r"C:\ProgramData\secret.conf",
    ])
    def test_deny_write_to_system_dirs_windows(self, policy, path):
        ok, reason = policy.is_path_allowed_write(path)
        assert ok is False, f"Write should be denied for {path}: {reason}"

    @pytest.mark.skipif(platform.system() == "Windows", reason="Linux-only")
    @pytest.mark.parametrize("path", [
        "/bin/bash",
        "/usr/lib/test.so",
        "/etc/passwd",
        "/boot/grub/grub.cfg",
    ])
    def test_deny_write_to_system_dirs_linux(self, policy, path):
        ok, reason = policy.is_path_allowed_write(path)
        assert ok is False, f"Write should be denied for {path}: {reason}"


# ── Workspace read allowed ─────────────────────────────────────────

class TestWorkspaceRead:
    def test_read_workspace_allowed(self, policy):
        ws_file = str(policy.workspace / "test.txt")
        ok, reason = policy.is_path_allowed_read(ws_file)
        assert ok is True, f"Read in workspace should be allowed: {reason}"

    def test_write_workspace_allowed(self, policy):
        ws_file = str(policy.workspace / "output.txt")
        ok, reason = policy.is_path_allowed_write(ws_file)
        assert ok is True, f"Write in workspace should be allowed: {reason}"


# ── Write outside workspace denied ─────────────────────────────────

class TestWriteOutsideWorkspace:
    def test_deny_write_outside_workspace(self, policy):
        if platform.system() == "Windows":
            path = r"C:\Users\Public\evil.txt"
        else:
            path = "/tmp/evil.txt"
        ok, reason = policy.is_path_allowed_write(path)
        assert ok is False, f"Write outside workspace should be denied: {reason}"


# ── Network denied by default ──────────────────────────────────────

class TestNetworkDenied:
    def test_network_off_by_default(self, policy):
        ok, reason = policy.is_network_allowed()
        assert ok is False

    def test_network_toggle_on(self, policy):
        policy.set_network(True)
        ok, reason = policy.is_network_allowed()
        assert ok is True

    def test_network_toggle_off(self, policy):
        policy.set_network(True)
        policy.set_network(False)
        ok, reason = policy.is_network_allowed()
        assert ok is False


# ── Path traversal ─────────────────────────────────────────────────

class TestPathTraversal:
    def test_deny_read_traversal(self, policy):
        ok, reason = policy.is_path_allowed_read("../../../etc/passwd")
        assert ok is False

    def test_deny_write_traversal(self, policy):
        ok, reason = policy.is_path_allowed_write("../../../tmp/evil.txt")
        assert ok is False


# ── Command allowlist ──────────────────────────────────────────────

class TestCommandAllowlist:
    def test_allowed_command(self, policy):
        ok, reason = policy.is_command_allowed(["whoami"])
        assert ok is True

    def test_denied_command(self, policy):
        ok, reason = policy.is_command_allowed(["rm", "-rf", "/"])
        assert ok is False

    def test_blocked_chars(self, policy):
        ok, reason = policy.is_command_allowed(["echo", "hello", ">", "file.txt"])
        assert ok is False
        assert "blocked character" in reason

    def test_pipe_blocked(self, policy):
        ok, reason = policy.is_command_allowed(["cat", "file.txt", "|", "grep", "secret"])
        assert ok is False


# ── Generic evaluate ───────────────────────────────────────────────

class TestEvaluate:
    def test_unknown_tool_denied(self, policy):
        from core.models import PolicyDecision
        decision, reason = policy.evaluate("evil_tool", {})
        assert decision == PolicyDecision.DENY

    def test_local_research_allowed(self, policy):
        from core.models import PolicyDecision
        decision, reason = policy.evaluate("research_local", {"query": "test"})
        assert decision == PolicyDecision.ALLOW

    def test_web_research_denied_by_default(self, policy):
        from core.models import PolicyDecision
        decision, reason = policy.evaluate("research_web", {"query": "test"})
        assert decision == PolicyDecision.DENY
