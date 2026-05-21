from __future__ import annotations

import re
from pathlib import Path


def test_web_theme_uses_approved_palette() -> None:
    css = Path("apps/web/src/styles.css").read_text(encoding="utf-8")
    approved = {
        "#4B6584",
        "#778CA3",
        "#A5B1C2",
        "#D1D8E0",
        "#3867D6",
        "#4B7BEC",
        "#20BF6B",
        "#F7B731",
        "#EB3B5A",
        "#2BCBBA",
    }

    assert set(re.findall(r"#[0-9A-Fa-f]{6}", css)) <= approved
    assert "rgba(" not in css

