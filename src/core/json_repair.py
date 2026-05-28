from __future__ import annotations

import json
import re


def _strip_markdown_codeblock(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        # Find first newline after opening backticks
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1 :]
        # Strip closing backticks
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    return stripped


def extract_json_object(raw_text: str) -> str:
    stripped = _strip_markdown_codeblock(raw_text.strip())
    # Handle JSON arrays: find the outermost [] that wraps objects
    if stripped.startswith("["):
        # Find matching closing bracket
        depth = 0
        for i, ch in enumerate(stripped):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return stripped[: i + 1]
        # If no matching bracket, fall through to object extraction
    # Handle JSON objects: find first { and last }
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return stripped[start : end + 1]


_UNESCAPED_CONTROL_RE = re.compile(r"(?<!\\)([\n\r\t])")


def _fix_unescaped_controls(json_text: str) -> str:
    """Replace literal newlines/tabs inside JSON string values with escaped forms."""
    result = []
    in_string = False
    escape = False
    for ch in json_text:
        if escape:
            result.append(ch)
            escape = False
            continue
        if ch == "\\":
            result.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch in "\n\r\t":
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            continue
        result.append(ch)
    return "".join(result)


def repair_json_text(raw_text: str) -> str:
    candidate = extract_json_object(raw_text).strip()
    candidate = _fix_unescaped_controls(candidate)
    json.loads(candidate)
    return candidate
