"""Context compression utilities."""

from __future__ import annotations


def compress_text(text: str, target_tokens: int) -> str:
    """Compress *text* to fit within *target_tokens*."""
    if target_tokens <= 0:
        return ""

    normalized_lines = [line.rstrip() for line in text.splitlines()]
    non_empty = [line for line in normalized_lines if line.strip()]
    if not non_empty:
        return ""

    compressed: list[str] = []
    seen: set[str] = set()
    words_used = 0
    for line in non_empty:
        normalized = " ".join(line.split()).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        words = line.split()
        remaining = target_tokens - words_used
        if remaining <= 0:
            break
        if len(words) > remaining:
            compressed.append(" ".join(words[:remaining]))
            break
        compressed.append(line)
        words_used += len(words)
    return "\n".join(compressed)
