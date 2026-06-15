#!/usr/bin/env python3
"""SessionStart hook payload: 检测当前项目 + 直接子目录的 pending handoff.

从 stdin 读 hook 输入 JSON (含 cwd / session_id / source).

行为:
  1. 扫 cwd + cwd 的直接子目录 (深度 ≤2), 找:
     - <dir>/rpiv/handoff-*.md
     - <dir>/handoff/handoff-*.md
  2. 解析每份 frontmatter, 过滤 status: pending
  3. 按 mtime 倒序排
  4. 通过 hookSpecificOutput.additionalContext 输出 markdown 提醒
  5. 项目外 (cwd 下完全无 handoff) 静默 exit 0
  6. 任何异常静默 exit 0 (绝不阻塞会话启动)
"""
import datetime
import json
import re
import sys
from pathlib import Path

BLACKLIST = {
    ".git", ".hg", ".svn",
    "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".next", "target", ".tox",
    ".idea", ".vscode", ".pytest_cache", ".ruff_cache",
    ".cache", ".tmp", "tmp",
}

STALE_DAYS = 7


def parse_frontmatter(file_path):
    """简单解析 yaml frontmatter, 返回 dict. 失败返回 {}."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}

    if not text.startswith("---"):
        return {}

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    result = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        if value.lower() in ("null", "none", "~", ""):
            value = None
        result[key] = value
    return result


def days_since(iso_str):
    """ISO 8601 → 距今天数. 解析失败返回 None."""
    if not iso_str:
        return None
    try:
        s = iso_str.replace("Z", "+00:00").split("+")[0].split(".")[0]
        dt = datetime.datetime.fromisoformat(s)
        return (datetime.datetime.now() - dt).days
    except (ValueError, AttributeError, TypeError):
        return None


def scan_dir_for_handoffs(target_dir):
    """扫单个目录的 rpiv/handoff-*.md 和 handoff/handoff-*.md."""
    results = []
    for subdir_name in ("rpiv", "handoff"):
        subdir = target_dir / subdir_name
        if not subdir.is_dir():
            continue
        try:
            for f in subdir.glob("handoff-*.md"):
                if not f.is_file():
                    continue
                fm = parse_frontmatter(f)
                if fm.get("status") != "pending":
                    continue

                updated_at = fm.get("updated_at")
                created_at = fm.get("created_at")
                anchor_iso = updated_at or created_at
                days = days_since(anchor_iso) if anchor_iso else None

                try:
                    mtime_ts = f.stat().st_mtime
                except OSError:
                    mtime_ts = 0

                if days is None:
                    try:
                        mtime_dt = datetime.datetime.fromtimestamp(mtime_ts)
                        days = (datetime.datetime.now() - mtime_dt).days
                    except (OSError, OverflowError, ValueError):
                        days = None

                results.append({
                    "path": f,
                    "mtime_ts": mtime_ts,
                    "anchor_iso": anchor_iso,
                    "description": fm.get("description") or "",
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "days_since": days,
                })
        except OSError:
            continue
    return results


def fmt_time_label(days):
    if days is None:
        return ""
    if days == 0:
        return "今天更新"
    if days == 1:
        return "1 天前更新"
    if days >= STALE_DAYS:
        return f"⚠️ 距今 {days} 天未消费"
    return f"{days} 天前更新"


def fmt_item(handoff, cwd_path, idx=None):
    try:
        rel = handoff["path"].relative_to(cwd_path)
    except ValueError:
        rel = handoff["path"]
    rel_str = str(rel).replace("\\", "/")

    prefix = f"  [{idx}]" if idx is not None else "  ·"
    time_label = fmt_time_label(handoff.get("days_since"))

    head = f"{prefix} `{rel_str}`"
    if time_label:
        head += f"  [{time_label}]"

    lines = [head]
    desc = handoff.get("description", "")
    if desc:
        lines.append(f"      📝 {desc}")
    lines.append(f"      → `/rpiv-loop:handoff --mark-consumed {rel_str}`")
    return lines


def main():
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        hook_input = {}

    cwd = hook_input.get("cwd", "") or ""
    if not cwd:
        return 0

    cwd_path = Path(cwd)
    if not cwd_path.is_dir():
        return 0

    all_handoffs = []

    cwd_handoffs = scan_dir_for_handoffs(cwd_path)
    for h in cwd_handoffs:
        h["scope"] = "current"
        h["project_label"] = "./"
    all_handoffs.extend(cwd_handoffs)

    try:
        for sub in sorted(cwd_path.iterdir()):
            if not sub.is_dir():
                continue
            if sub.name in BLACKLIST or sub.name.startswith("."):
                continue
            sub_handoffs = scan_dir_for_handoffs(sub)
            for h in sub_handoffs:
                h["scope"] = "subdir"
                h["project_label"] = f"{sub.name}/"
            all_handoffs.extend(sub_handoffs)
    except OSError:
        pass

    if not all_handoffs:
        return 0

    # 排序: 优先 frontmatter updated_at (Edit 模式会更新), fallback mtime, 最新在前
    all_handoffs.sort(
        key=lambda h: (h.get("anchor_iso") or "", h.get("mtime_ts", 0)),
        reverse=True,
    )

    total = len(all_handoffs)
    parts = [
        f"🎯 检测到 **{total} 份 pending handoff** (cwd: `{cwd}`):",
        "",
    ]

    current_items = [h for h in all_handoffs if h["scope"] == "current"]
    subdir_items = [h for h in all_handoffs if h["scope"] == "subdir"]

    if current_items:
        parts.append(f"📍 **当前项目 (./)** - {len(current_items)} 条:")
        for i, h in enumerate(current_items, 1):
            parts.extend(fmt_item(h, cwd_path, idx=i))
        parts.append("")

    if subdir_items:
        by_label = {}
        for h in subdir_items:
            by_label.setdefault(h["project_label"], []).append(h)
        for label, items in by_label.items():
            parts.append(f"📂 **子项目 {label}** - {len(items)} 条:")
            for h in items:
                parts.extend(fmt_item(h, cwd_path))
            parts.append("")

    parts.extend([
        "---",
        "**请在本次会话开头主动用 AskUserQuestion 询问用户:**",
        "- 是否要 mark-consumed 某份 handoff 并按其 bootstrap prompt 推进",
        "- 还是先做别的 (跳过本次提醒)",
        "",
        "注意: 单纯 Read handoff 不会改 status, 必须显式调 `/rpiv-loop:handoff --mark-consumed <path>`.",
    ])

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(parts),
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
