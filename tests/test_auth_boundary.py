"""Regression tests for Phase 1 trust boundaries.

Covers backend auth, shell intent classification, filesystem boundaries,
symlink hardening, and approval consistency.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentheim_code.backend import create_app
from core.path_security import safe_workspace_file_path
from core.policy_engine import PolicyConfig, PolicyEngine
from core.shell_intent import ShellIntent, classify_shell_intent
from core.tool_invocation import resolve_operation_risk
from core.tool_protocol import RiskLevel, ToolContext
from tools.filesystem import FilesystemTool


@pytest.fixture
def workspace_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def client(workspace_dir: str):
    app = create_app(workspace_dir)
    return TestClient(app, headers={"x-agentheim-token": app.state.auth_token})


@pytest.fixture
def client_no_auth(workspace_dir: str):
    app = create_app(workspace_dir)
    return TestClient(app)


class TestBackendAuth:
    def test_unauthenticated_request_rejected(self, client_no_auth: TestClient) -> None:
        resp = client_no_auth.get("/api/health")
        assert resp.status_code == 401
        detail = resp.json()["detail"]
        assert detail["error_code"] == "E2011"

    def test_authenticated_happy_path(self, client: TestClient, workspace_dir: str) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert workspace_dir in data["workspace"]

    def test_wrong_token_rejected(self, client_no_auth: TestClient) -> None:
        resp = client_no_auth.get("/api/health", headers={"x-agentheim-token": "bad-token"})
        assert resp.status_code == 401

    def test_token_injected_into_index(self, client: TestClient) -> None:
        resp = client.get("/coder")
        assert resp.status_code == 200
        assert "window.__AGENTHEIM_TOKEN__" in resp.text

    def test_token_persisted_to_file(self, workspace_dir: str) -> None:
        app = create_app(workspace_dir)
        token_path = Path(workspace_dir) / ".ai-team" / ".session-token"
        assert token_path.exists()
        assert token_path.read_text(encoding="utf-8") == app.state.auth_token


class TestShellIntentClassification:
    def test_read_only_commands(self) -> None:
        assert classify_shell_intent(["ls", "-la"]) == ShellIntent.READ_ONLY
        assert classify_shell_intent(["git", "status"]) == ShellIntent.READ_ONLY
        assert classify_shell_intent(["git", "diff"]) == ShellIntent.READ_ONLY
        assert classify_shell_intent(["cat", "file.txt"]) == ShellIntent.READ_ONLY

    def test_build_test_commands(self) -> None:
        assert classify_shell_intent(["pytest"]) == ShellIntent.BUILD_TEST
        assert classify_shell_intent(["python", "-m", "pytest"]) == ShellIntent.BUILD_TEST
        assert classify_shell_intent(["npm", "test"]) == ShellIntent.BUILD_TEST
        assert classify_shell_intent(["cargo", "build"]) == ShellIntent.BUILD_TEST
        assert classify_shell_intent(["go", "test"]) == ShellIntent.BUILD_TEST
        assert classify_shell_intent(["dotnet", "test"]) == ShellIntent.BUILD_TEST

    def test_package_commands(self) -> None:
        assert classify_shell_intent(["pip", "install", "requests"]) == ShellIntent.PACKAGE
        assert classify_shell_intent(["npm", "install"]) == ShellIntent.PACKAGE
        assert classify_shell_intent(["cargo", "add", "serde"]) == ShellIntent.PACKAGE
        assert classify_shell_intent(["python", "-m", "pip", "install"]) == ShellIntent.PACKAGE

    def test_eval_commands(self) -> None:
        assert classify_shell_intent(["python", "-c", "print(1)"]) == ShellIntent.EVAL
        assert classify_shell_intent(["node", "-e", "console.log(1)"]) == ShellIntent.EVAL
        assert classify_shell_intent(["python", "-m", "unknown"]) == ShellIntent.EVAL

    def test_networked_commands(self) -> None:
        assert (
            classify_shell_intent(["git", "clone", "https://example.com/repo.git"])
            == ShellIntent.NETWORKED
        )
        assert classify_shell_intent(["git", "push"]) == ShellIntent.NETWORKED
        assert classify_shell_intent(["curl", "https://example.com"]) == ShellIntent.NETWORKED

    def test_unknown_commands(self) -> None:
        assert classify_shell_intent(["python", "script.py"]) == ShellIntent.UNKNOWN
        assert classify_shell_intent(["node", "script.js"]) == ShellIntent.UNKNOWN
        assert classify_shell_intent(["some_tool"]) == ShellIntent.UNKNOWN

    def test_resolve_risk_maps_intent(self) -> None:
        assert (
            resolve_operation_risk("shell.execute", {"command": ["ls"]}, RiskLevel.HIGH)
            == RiskLevel.LOW
        )
        assert (
            resolve_operation_risk("shell.execute", {"command": ["pytest"]}, RiskLevel.HIGH)
            == RiskLevel.MEDIUM
        )
        assert (
            resolve_operation_risk("shell.execute", {"command": ["pip", "install"]}, RiskLevel.HIGH)
            == RiskLevel.HIGH
        )
        assert (
            resolve_operation_risk(
                "shell.execute", {"command": ["python", "-c", "print(1)"]}, RiskLevel.HIGH
            )
            == RiskLevel.HIGH
        )
        assert (
            resolve_operation_risk(
                "shell.execute", {"command": ["git", "clone", "..."]}, RiskLevel.HIGH
            )
            == RiskLevel.CRITICAL
        )


class TestPolicyEngineShellIntent:
    def test_local_only_denies_networked_shell(self) -> None:
        engine = PolicyEngine(PolicyConfig(local_only=True))
        context = ToolContext()
        decision = engine.evaluate(
            "shell.execute", {"command": ["git", "clone", "https://x"]}, context, RiskLevel.HIGH
        )
        assert decision.decision == "deny"
        assert "local_only" in decision.policy_id

    def test_local_only_allows_read_only_shell(self) -> None:
        engine = PolicyEngine(PolicyConfig(local_only=True))
        context = ToolContext()
        decision = engine.evaluate("shell.execute", {"command": ["ls"]}, context, RiskLevel.LOW)
        assert decision.decision == "allow"


class TestFilesystemBoundary:
    def test_path_traversal_denied(self, workspace_dir: str) -> None:
        tool = FilesystemTool(workspace_dir)
        context = ToolContext(allowed_paths=[workspace_dir])
        result = tool.invoke({"operation": "read", "path": "../outside.txt"}, context)
        assert not result.success
        assert "escapes" in result.error.lower() or "outside" in result.error.lower()

    def test_symlink_escape_denied(self, workspace_dir: str) -> None:
        workspace = Path(workspace_dir)
        outside = workspace.parent / "outside_secret.txt"
        outside.write_text("secret", encoding="utf-8")
        link = workspace / "bad_link"
        link.symlink_to(outside)

        tool = FilesystemTool(workspace_dir)
        context = ToolContext(allowed_paths=[workspace_dir])
        result = tool.invoke({"operation": "read", "path": "bad_link"}, context)
        assert not result.success
        assert "escapes" in result.error.lower() or "outside" in result.error.lower()

    def test_dot_git_denied(self, workspace_dir: str) -> None:
        tool = FilesystemTool(workspace_dir)
        context = ToolContext(allowed_paths=[workspace_dir])
        result = tool.invoke({"operation": "read", "path": ".git/config"}, context)
        assert not result.success
        assert "protected" in result.error.lower() or "denied" in result.error.lower()

    def test_ai_team_denied(self, workspace_dir: str) -> None:
        tool = FilesystemTool(workspace_dir)
        context = ToolContext(allowed_paths=[workspace_dir])
        result = tool.invoke({"operation": "read", "path": ".ai-team/session-token"}, context)
        assert not result.success
        assert "protected" in result.error.lower() or "denied" in result.error.lower()

    def test_safe_workspace_file_path_helper(self, tmp_path: Path) -> None:
        assert safe_workspace_file_path(tmp_path, "src/main.py").name == "main.py"
        with pytest.raises(ValueError, match="escapes"):
            safe_workspace_file_path(tmp_path, "../secret")
        with pytest.raises(ValueError, match="protected"):
            safe_workspace_file_path(tmp_path, ".git/config")
        with pytest.raises(ValueError, match="protected"):
            safe_workspace_file_path(tmp_path, ".ai-team/token")


class TestApprovalConsistency:
    def test_shell_build_test_asks_in_ask_mode(self) -> None:
        from workflows.coder.action_engine import _policy_config
        from workflows.coder.models import TrustMode

        config = _policy_config(TrustMode.ASK)
        engine = PolicyEngine(config)
        context = ToolContext()
        decision = engine.evaluate(
            "shell.execute",
            {"command": ["pytest"]},
            context,
            resolve_operation_risk("shell.execute", {"command": ["pytest"]}, RiskLevel.HIGH),
        )
        assert decision.decision == "ask"

    def test_shell_package_asks_in_ask_mode(self) -> None:
        from workflows.coder.action_engine import _policy_config
        from workflows.coder.models import TrustMode

        config = _policy_config(TrustMode.ASK)
        engine = PolicyEngine(config)
        context = ToolContext()
        decision = engine.evaluate(
            "shell.execute",
            {"command": ["pip", "install", "x"]},
            context,
            resolve_operation_risk(
                "shell.execute", {"command": ["pip", "install", "x"]}, RiskLevel.HIGH
            ),
        )
        assert decision.decision == "ask"

    def test_filesystem_write_asks_in_ask_mode(self) -> None:
        from workflows.coder.action_engine import _policy_config
        from workflows.coder.models import TrustMode

        config = _policy_config(TrustMode.ASK)
        engine = PolicyEngine(config)
        context = ToolContext()
        decision = engine.evaluate(
            "filesystem",
            {"operation": "write", "path": "foo.py", "content": "x"},
            context,
            resolve_operation_risk(
                "filesystem",
                {"operation": "write", "path": "foo.py", "content": "x"},
                RiskLevel.NONE,
            ),
        )
        assert decision.decision == "ask"

    def test_network_denied_by_default(self) -> None:
        engine = PolicyEngine(PolicyConfig(network_allowed=False))
        context = ToolContext()
        decision = engine.evaluate(
            "http.request", {"url": "https://example.com"}, context, RiskLevel.HIGH
        )
        assert decision.decision == "deny"
        assert "network" in decision.reason.lower()

    def test_similar_risk_produces_similar_decision(self) -> None:
        """High-risk shell and high-risk file actions should behave consistently."""
        from workflows.coder.action_engine import _policy_config
        from workflows.coder.models import TrustMode

        config = _policy_config(TrustMode.ASK)
        engine = PolicyEngine(config)
        context = ToolContext()

        shell_decision = engine.evaluate(
            "shell.execute",
            {"command": ["pip", "install", "x"]},
            context,
            RiskLevel.HIGH,
        )
        file_decision = engine.evaluate(
            "filesystem",
            {"operation": "write", "path": "x.py", "content": "x"},
            context,
            RiskLevel.HIGH,
        )
        assert shell_decision.decision == file_decision.decision == "ask"
