"""Tests for the bounded context bundle pipeline."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agentheim_code.context_bundle import build_context_bundle


def test_empty_bundle() -> None:
    with tempfile.TemporaryDirectory() as d:
        bundle = build_context_bundle(Path(d), [])
    assert bundle.items == []
    assert bundle.errors == []
    assert bundle.total_token_estimate() == 0


def test_ok_file_with_preview() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "readme.md"
        path.write_text("# Hello\nworld", encoding="utf-8")
        bundle = build_context_bundle(Path(d), ["readme.md"])
    assert len(bundle.items) == 1
    item = bundle.items[0]
    assert item.status == "ok"
    assert item.path == "readme.md"
    assert item.preview == "# Hello\nworld"
    assert item.token_estimate() > 0


def test_missing_file_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        bundle = build_context_bundle(Path(d), ["missing.txt"])
    assert len(bundle.items) == 1
    assert bundle.items[0].status == "missing"
    assert "does not exist" in bundle.errors[0]


def test_binary_file_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "data.bin"
        path.write_bytes(b"\x00\x01\x02\x03")
        bundle = build_context_bundle(Path(d), ["data.bin"])
    assert len(bundle.items) == 1
    assert bundle.items[0].status == "binary"
    assert "binary" in bundle.errors[0]


def test_huge_file_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "huge.txt"
        path.write_text("x" * 200_000, encoding="utf-8")
        bundle = build_context_bundle(Path(d), ["huge.txt"])
    assert len(bundle.items) == 1
    assert bundle.items[0].status == "huge"
    assert "too large" in bundle.errors[0]


def test_ignored_git_file_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        git_dir = Path(d) / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("secret", encoding="utf-8")
        bundle = build_context_bundle(Path(d), [".git/config"])
    assert len(bundle.items) == 1
    assert bundle.items[0].status == "ignored"
    assert "ignored" in bundle.errors[0]


def test_path_traversal_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "secret.txt"
        path.write_text("secret", encoding="utf-8")
        bundle = build_context_bundle(Path(d), ["../secret.txt"])
    assert len(bundle.items) == 1
    assert bundle.items[0].status == "outside_workspace"
    assert "outside" in bundle.errors[0].lower() or "traverses" in bundle.errors[0].lower()


def test_absolute_path_outside_workspace_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        other = Path(d).parent / "other.txt"
        other.write_text("other", encoding="utf-8")
        bundle = build_context_bundle(Path(d), [str(other)])
    assert len(bundle.items) == 1
    assert bundle.items[0].status == "outside_workspace"


def test_bundle_prompt_block_includes_content() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "app.py"
        path.write_text("print(1)", encoding="utf-8")
        bundle = build_context_bundle(Path(d), ["app.py"])
    block = bundle.to_prompt_block()
    assert "<context_files>" in block
    assert 'path="app.py"' in block
    assert "print(1)" in block
    assert "</context_files>" in block


def test_bundle_preview_payload() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "app.py"
        path.write_text("print(1)", encoding="utf-8")
        bundle = build_context_bundle(Path(d), ["app.py"])
    payload = bundle.to_preview_payload()
    assert len(payload) == 1
    assert payload[0]["path"] == "app.py"
    assert payload[0]["status"] == "ok"
    assert payload[0]["token_estimate"] > 0


def test_truncation_for_large_text() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "long.txt"
        path.write_text("a" * 10_000, encoding="utf-8")
        bundle = build_context_bundle(Path(d), ["long.txt"])
    item = bundle.items[0]
    assert item.status == "ok"
    assert len(item.preview) < 10_000
    assert "truncated" in item.truncation_reason


def test_duplicate_paths_deduplicated() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "a.txt"
        path.write_text("x", encoding="utf-8")
        bundle = build_context_bundle(Path(d), ["a.txt", "a.txt"])
    assert len(bundle.items) == 1
