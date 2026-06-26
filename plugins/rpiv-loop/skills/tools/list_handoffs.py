#!/usr/bin/env python3
"""列出 cwd + 直接子目录的 handoff 文件 (markdown 表格输出, 不需 LLM 思考).

用法:
    python list_handoffs.py [--cwd <dir>] [--all]

默认:
    - cwd = os.getcwd()
    - 只列 status: pending
    - 扫 cwd/rpiv/, cwd/handoff/, 以及 cwd 下一级子目录的同名子目录

--all 选项额外列出 archived 文件 (单独一段, 不混在 pending 表里).
"""
import argparse
import os
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent.parent / "hooks"
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

from handoff_detector import (  # noqa: E402
    BLACKLIST,
    days_since,
    fmt_time_label,
    is_handoff_name,
    parse_frontmatter,
)


def scan_dir(target_dir, statuses=("pending",)):
    results = []
    subdir_names = ["rpiv", "handoff"]
    # 已消费 handoff 在 mark-consumed 时即挪进 <handoff_dir>/archive/,
    # 故查 archived 须额外扫归档子目录;pending 永远在根目录,无需扫 archive/.
    if "archived" in statuses:
        subdir_names += ["rpiv/archive", "handoff/archive"]
    for subdir_name in subdir_names:
        subdir = target_dir / subdir_name
        if not subdir.is_dir():
            continue
        try:
            for f in subdir.glob("*.md"):
                if not f.is_file() or not is_handoff_name(f.name):
                    continue
                fm = parse_frontmatter(f)
                status = fm.get("status")
                if status not in statuses:
                    continue
                anchor_iso = fm.get("updated_at") or fm.get("created_at")
                results.append({
                    "path": f,
                    "status": status,
                    "description": fm.get("description") or "",
                    "created_at": fm.get("created_at"),
                    "updated_at": fm.get("updated_at"),
                    "consumed_at": fm.get("consumed_at"),
                    "days_since": days_since(anchor_iso),
                    "anchor_iso": anchor_iso,
                })
        except OSError:
            continue
    return results


def collect(cwd_path, statuses):
    all_results = []
    cwd_results = scan_dir(cwd_path, statuses)
    for h in cwd_results:
        h["scope"] = "current"
        h["project_label"] = "./"
    all_results.extend(cwd_results)

    try:
        for sub in sorted(cwd_path.iterdir()):
            if not sub.is_dir():
                continue
            if sub.name in BLACKLIST or sub.name.startswith("."):
                continue
            sub_results = scan_dir(sub, statuses)
            for h in sub_results:
                h["scope"] = "subdir"
                h["project_label"] = f"{sub.name}/"
            all_results.extend(sub_results)
    except OSError:
        pass

    all_results.sort(
        key=lambda h: (h.get("anchor_iso") or "", str(h["path"])),
        reverse=True,
    )
    return all_results


def render_section(title, items, cwd_path, show_status=False):
    lines = [f"## {title}", ""]
    if not items:
        lines.append("_(无)_")
        lines.append("")
        return lines

    by_label = {}
    for h in items:
        by_label.setdefault(h["project_label"], []).append(h)

    for label, hs in by_label.items():
        lines.append(f"### {label}")
        lines.append("")
        for i, h in enumerate(hs, 1):
            try:
                rel = h["path"].relative_to(cwd_path)
            except ValueError:
                rel = h["path"]
            rel_str = str(rel).replace("\\", "/")
            time_label = fmt_time_label(h.get("days_since"))
            status_chip = f"[{h['status']}] " if show_status else ""
            head = f"- {status_chip}**`{rel_str}`**"
            if time_label:
                head += f" — {time_label}"
            lines.append(head)
            desc = h.get("description", "")
            if desc:
                lines.append(f"  - 📝 {desc}")
            if h["status"] == "pending":
                lines.append(f"  - → `/rpiv-loop:handoff --mark-consumed {rel_str}`")
        lines.append("")
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--all", action="store_true", help="额外列 archived")
    args = parser.parse_args()

    cwd_path = Path(args.cwd).resolve()
    if not cwd_path.is_dir():
        print(f"cwd 不是目录: {cwd_path}")
        return 1

    pending = collect(cwd_path, statuses=("pending",))

    lines = [f"# Handoff 列表 (cwd: `{cwd_path}`)", ""]
    lines.extend(render_section(f"⏸️ Pending ({len(pending)} 条)", pending, cwd_path))

    if args.all:
        archived = collect(cwd_path, statuses=("archived",))
        lines.extend(render_section(
            f"✅ Archived ({len(archived)} 条)", archived, cwd_path, show_status=False
        ))

    if not pending and not args.all:
        lines.append("_当前项目无 pending handoff。如需查看历史已消费记录, 加 `--all` 重跑.._")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
