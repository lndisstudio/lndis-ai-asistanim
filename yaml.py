"""Minimal YAML subset parser exposing safe_load for offline use.
This is intentionally limited to the structures used by policy/default_policy.yaml.
"""

from __future__ import annotations

from typing import Any


def _clean(line: str) -> str:
    return line.split("#", 1)[0].rstrip("\n")


def _indent_and_text(line: str) -> tuple[int, str]:
    cleaned = _clean(line).rstrip()
    if not cleaned.strip():
        return -1, ""
    indent = len(cleaned) - len(cleaned.lstrip(" "))
    return indent, cleaned.strip()


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if text == "":
        return ""
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if text.lstrip("-").isdigit():
        return int(text)
    return text


def safe_load(content: Any) -> dict[str, Any]:
    if hasattr(content, "read"):
        content = content.read()
    lines = str(content).splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    i = 0
    while i < len(lines):
        indent, text = _indent_and_text(lines[i])
        if indent < 0:
            i += 1
            continue

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if text.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError("Invalid YAML: list item under non-list parent")
            parent.append(_parse_scalar(text[2:]))
            i += 1
            continue

        if ":" not in text:
            raise ValueError(f"Invalid YAML line: {text}")

        key, value = text.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value:
            if not isinstance(parent, dict):
                raise ValueError("Invalid YAML: key-value under non-dict parent")
            parent[key] = _parse_scalar(value)
            i += 1
            continue

        # nested block: choose list/dict based on next meaningful child line
        next_container: Any = {}
        j = i + 1
        while j < len(lines):
            n_indent, n_text = _indent_and_text(lines[j])
            if n_indent < 0:
                j += 1
                continue
            if n_indent <= indent:
                break
            if n_text.startswith("- "):
                next_container = []
            break

        if not isinstance(parent, dict):
            raise ValueError("Invalid YAML: nested mapping under non-dict parent")
        parent[key] = next_container
        stack.append((indent, next_container))
        i += 1

    return root
