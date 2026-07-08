#!/usr/bin/env python3
"""UserPromptSubmit hook: 首次注入 pending handoff 提醒到 user prompt 之前.

跟 handoff_detector.py (SessionStart) 不同:
- detector 输出 system context (additionalContext via SessionStart), LLM 可能看到但不一定优先响应
- 本 hook 输出 user prompt prefix (additionalContext via UserPromptSubmit), Claude 必看必处理

为避免每条 user prompt 都注入, 用 RPIV_STATE_DIR（未设置时为通用 rpiv-loop 状态目录）下的
handoff_first_prompt_seen.json 跟踪
已注入过的 session_id, 同一会话只注入一次 (会话首条 user prompt).

任何异常静默 exit 0, 绝不阻塞 user prompt 提交.
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

from handoff_detector import (  # noqa: E402
    collect_handoffs,
    fmt_item,
)

STATE_DIR = Path(os.environ.get("RPIV_STATE_DIR", Path.home() / ".rpiv-loop"))
SEEN_FILE = STATE_DIR / "handoff_first_prompt_seen.json"
LOG_FILE = STATE_DIR / "handoff_first_prompt.log"
MAX_SEEN = 200


def load_seen():
    try:
        with SEEN_FILE.open(encoding="utf-8") as fp:
            data = json.load(fp)
        sessions = data.get("sessions", [])
        if isinstance(sessions, list):
            return sessions
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return []


def save_seen(sessions):
    try:
        SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        trimmed = sessions[-MAX_SEEN:]
        fd, tmp_path = tempfile.mkstemp(
            prefix=".handoff_first_prompt_seen.", suffix=".tmp", dir=str(SEEN_FILE.parent)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump({"sessions": trimmed}, fp, ensure_ascii=False)
        os.replace(tmp_path, SEEN_FILE)
    except OSError:
        pass


def render_prompt_prefix(handoffs, cwd):
    total = len(handoffs)
    parts = [
        "🚨 **优先处理 pending handoff** (在响应用户本次请求之前):",
        "",
        f"检测到 {total} 份 pending handoff (cwd: `{cwd}`):",
        "",
    ]

    current_items = [h for h in handoffs if h["scope"] == "current"]
    subdir_items = [h for h in handoffs if h["scope"] == "subdir"]
    cwd_path = Path(cwd)

    if current_items:
        parts.append(f"📍 当前项目 (./) - {len(current_items)} 条:")
        for i, h in enumerate(current_items, 1):
            parts.extend(fmt_item(h, cwd_path, idx=i))
        parts.append("")

    if subdir_items:
        by_label = {}
        for h in subdir_items:
            by_label.setdefault(h["project_label"], []).append(h)
        for label, items in by_label.items():
            parts.append(f"📂 子项目 {label} - {len(items)} 条:")
            for h in items:
                parts.extend(fmt_item(h, cwd_path))
            parts.append("")

    parts.extend([
        "---",
        "**强制行为 (本会话首条 user prompt, 后续不再注入)**:",
        "1. 立刻简洁询问用户是否要 mark-consumed 某份 handoff 并按其 bootstrap prompt 推进, 还是先做别的",
        "2. 如果用户选 mark-consumed: 调 `/rpiv-loop:handoff --mark-consumed <path>` 并按文件顶部的 bootstrap prompt 接续工作",
        "3. 如果用户选跳过: 才开始处理用户本条 prompt 的原始请求",
        "",
        "不要静默忽略本提醒去直接处理用户的请求.",
    ])

    return "\n".join(parts)


def main():
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return 0

    cwd = hook_input.get("cwd") or ""
    session_id = hook_input.get("session_id") or ""

    if not cwd or not session_id:
        return 0

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fp:
            fp.write(
                f"[{datetime.datetime.now().isoformat()}] "
                f"cwd={cwd} session_id={session_id}\n"
            )
    except OSError:
        pass

    seen = load_seen()
    if session_id in seen:
        return 0

    cwd_path = Path(cwd)
    if not cwd_path.is_dir():
        return 0

    handoffs = collect_handoffs(cwd_path)
    if not handoffs:
        seen.append(session_id)
        save_seen(seen)
        return 0

    seen.append(session_id)
    save_seen(seen)

    prefix = render_prompt_prefix(handoffs, cwd)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": prefix,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
