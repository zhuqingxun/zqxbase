#!/usr/bin/env python3
"""RPIV frontmatter status 合法性校验 hook（PostToolUse）。

对 `rpiv/**/*.md` 的 Write/Edit/MultiEdit 写入进行事后校验：若 frontmatter 的
status 字段不在合法枚举内，退出码 2 + stderr 提示，让 Claude 立即修复。

规范来源：rpiv-loop 插件 references/frontmatter-spec.md
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LEGAL_STATUS = {
    "process": {"pending", "in-progress", "completed", "superseded", "archived"},
    "todo": {"open", "in-progress", "completed", "archived"},
    "aux": {"pending", "completed", "archived"},
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
STATUS_RE = re.compile(r"^status:\s*([^\s#]+)\s*$", re.MULTILINE)


def classify(posix_path: str) -> str:
    if "/rpiv/todo/" in posix_path:
        return "todo"
    name = Path(posix_path).name
    if name.startswith(("brainstorm-summary-", "research-")):
        return "aux"
    return "process"


def extract_status(text: str) -> str | None:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    sm = STATUS_RE.search(m.group(1))
    if not sm:
        return None
    return sm.group(1).strip().strip("\"'")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") not in {"Write", "Edit", "MultiEdit"}:
        return 0

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0

    posix = Path(file_path).as_posix()
    if "/rpiv/" not in posix or not posix.endswith(".md"):
        return 0
    if "/rpiv/archive/" in posix:
        return 0

    try:
        text = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return 0

    status = extract_status(text)
    if status is None:
        return 0

    category = classify(posix)
    legal = LEGAL_STATUS[category]
    if status in legal:
        return 0

    sys.stderr.write(
        "[rpiv-loop] frontmatter status 非法\n"
        f"  文件: {posix}\n"
        f"  当前值: {status!r}\n"
        f"  文件类型: {category}\n"
        f"  合法枚举: {sorted(legal)}\n"
        "  规范: rpiv-loop 插件 references/frontmatter-spec.md\n"
        "  请将 status 改为合法值后重试（例如 draft → pending 或 in-progress）。\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
