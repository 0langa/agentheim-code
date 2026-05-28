from core.tool_invocation import resolve_operation_risk
from core.tool_protocol import RiskLevel


def test_shell_read_only_ls_is_low_risk() -> None:
    risk = resolve_operation_risk(
        "shell.execute",
        {"command": ["ls", "-la"]},
        RiskLevel.HIGH,
    )
    assert risk == RiskLevel.LOW


def test_shell_git_status_is_low_risk() -> None:
    risk = resolve_operation_risk(
        "shell.execute",
        {"command": ["git", "status"]},
        RiskLevel.HIGH,
    )
    assert risk == RiskLevel.LOW


def test_shell_python_eval_is_high_risk() -> None:
    risk = resolve_operation_risk(
        "shell.execute",
        {
            "command": [
                "python",
                "-c",
                "with open('approval-smoke.txt') as f: assert f.read() == 'hi'",
            ]
        },
        RiskLevel.HIGH,
    )
    assert risk == RiskLevel.HIGH


def test_shell_python_write_snippet_stays_high_risk() -> None:
    risk = resolve_operation_risk(
        "shell.execute",
        {
            "command": [
                "python",
                "-c",
                "with open('approval-smoke.txt', 'w') as f: f.write('hi')",
            ]
        },
        RiskLevel.HIGH,
    )
    assert risk == RiskLevel.HIGH


def test_shell_pytest_is_medium_risk() -> None:
    risk = resolve_operation_risk(
        "shell.execute",
        {"command": ["pytest", "-q"]},
        RiskLevel.HIGH,
    )
    assert risk == RiskLevel.MEDIUM


def test_shell_pip_install_is_high_risk() -> None:
    risk = resolve_operation_risk(
        "shell.execute",
        {"command": ["pip", "install", "requests"]},
        RiskLevel.HIGH,
    )
    assert risk == RiskLevel.HIGH


def test_shell_git_clone_is_critical_risk() -> None:
    risk = resolve_operation_risk(
        "shell.execute",
        {"command": ["git", "clone", "https://example.com/repo.git"]},
        RiskLevel.HIGH,
    )
    assert risk == RiskLevel.CRITICAL


def test_filesystem_read_is_none_risk() -> None:
    risk = resolve_operation_risk(
        "filesystem",
        {"operation": "read", "path": "foo.py"},
        RiskLevel.NONE,
    )
    assert risk == RiskLevel.NONE


def test_filesystem_write_is_medium_risk() -> None:
    risk = resolve_operation_risk(
        "filesystem",
        {"operation": "write", "path": "foo.py", "content": "x"},
        RiskLevel.NONE,
    )
    assert risk == RiskLevel.MEDIUM
