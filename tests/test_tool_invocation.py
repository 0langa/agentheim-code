from core.tool_invocation import resolve_operation_risk
from core.tool_protocol import RiskLevel


def test_shell_read_only_python_verification_is_low_risk() -> None:
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
    assert risk == RiskLevel.LOW


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
