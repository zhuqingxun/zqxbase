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
    # handoff 是跨会话交接票据，状态机仅 pending→archived（见 frontmatter-spec.md「Handoff 文件」）。
    # 它常物理落在 rpiv/todo/ 下，但语义不是 todo，必须独立枚举，否则 pending 被误判非法。
    "handoff": {"pending", "archived"},
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
STATUS_RE = re.compile(r"^status:\s*([^\s#]+)\s*$", re.MULTILINE)
TYPE_RE = re.compile(r"^type:\s*([^\s#]+)\s*$", re.MULTILINE)


def classify(posix_path: str, file_type: str | None = None) -> str:
    name = Path(posix_path).name
    # handoff 优先于 todo 判定：handoff 文件常落在 rpiv/todo/，先按 frontmatter type
    # 或文件名（标准 handoff-* 前缀 / 历史 *-HANDOFF 后缀，均含 "handoff"）识别，
    # 避免被路径规则归成 todo（todo 枚举无 pending，会误拒 handoff 的合法 pending）。
    if file_type == "handoff" or "handoff" in name.lower():
        return "handoff"
    if "/rpiv/todo/" in posix_path:
        return "todo"
    if name.startswith(("brainstorm-summary-", "research-")):
        return "aux"
    return "process"


def _search_frontmatter(text: str, pattern: re.Pattern[str]) -> str | None:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    sm = pattern.search(m.group(1))
    if not sm:
        return None
    return sm.group(1).strip().strip("\"'")


def extract_status(text: str) -> str | None:
    return _search_frontmatter(text, STATUS_RE)


def extract_type(text: str) -> str | None:
    return _search_frontmatter(text, TYPE_RE)


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

    category = classify(posix, extract_type(text))
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
