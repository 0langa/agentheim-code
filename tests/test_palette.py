from __future__ import annotations

import re
from pathlib import Path


def test_web_theme_uses_approved_palette() -> None:
    css = Path("apps/web/src/styles.css").read_text(encoding="utf-8")
    required_tokens = {
        "--app-bg",
        "--panel",
        "--surface",
        "--accent",
        "--success",
        "--warning",
        "--error",
        "--ai",
    }

    for token in required_tokens:
        assert token in css

    assert ':root[data-theme="light"]' in css
    assert ':root[data-theme="high_contrast"]' in css
    assert re.search(r"--accent:\s*#[0-9A-Fa-f]{6};", css)
    assert re.search(r"--error:\s*#[0-9A-Fa-f]{6};", css)
    assert "box-shadow:" in css
