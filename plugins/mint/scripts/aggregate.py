# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""aggregate.py — workspace-view 运行时聚合构造器

暴露 `build_workspace_view(root) -> dict`，构造 PRD 8.2 定义的 workspace-view 内存对象。
不持久化任何数据（PRD 原则 4）——仅 Read meta.yaml + workspace.yaml 后组装。

设计点：
- skills/next 内部调用此函数避免与 meta_io.scan_meetings 逻辑漂移
- 被 PERF-04 用 tracemalloc 测量（20 会议 peak < 10 MB）
- 不启动进程、不缓存、不写盘

CLI 子命令：
    --ws <workspace_root>                  输出 JSON workspace-view
    --ws <workspace_root> --active <dir>   显式声明 active 会议
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 允许作为脚本或模块导入：优先尝试 package 形式（不存在则 sys.path 兜底）
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import meta_io  # noqa: E402


def _resolve_active(root: Path, meetings: list[dict], explicit: str | None) -> dict:
    """按 PRD 6.4 推断 active 会议。仅用于 workspace-view.active 字段展示，不影响规则引擎"""
    if explicit:
        for m in meetings:
            if m.get("dir") == explicit:
                return {"dir": explicit, "resolved_by": "explicit"}
        return {"dir": explicit, "resolved_by": "explicit"}

    # 无 cwd 信号 → last_action 兜底
    if not meetings:
        return {"dir": None, "resolved_by": None}
    candidates = [m for m in meetings if m.get("last_action")]
    if not candidates:
        return {"dir": None, "resolved_by": None}
    top = max(candidates, key=lambda m: m.get("last_action") or "")
    return {"dir": top.get("dir"), "resolved_by": "last_action"}


def build_workspace_view(root: Path | str, active_dir: str | None = None) -> dict:
    """构造 workspace-view 内存对象

    Args:
        root: 工作区根（含 .mint/workspace.yaml）
        active_dir: 可选显式 active（PRD 6.4 优先级 1），不给则 last_action 兜底

    Returns:
        dict 结构（PRD 8.2）：
            {
                workspace: {name, root_path, scanned_at, scenario},
                intent:    {goal, deliverables},
                meetings:  [...scan_meetings 摘要],
                active:    {dir, resolved_by}
            }

    Raises:
        FileNotFoundError: workspace.yaml 缺失
    """
    root = Path(root).resolve()
    ws_yaml = root / ".mint" / "workspace.yaml"
    if not ws_yaml.is_file():
        raise FileNotFoundError(f"workspace.yaml 不存在: {ws_yaml}")

    ws_data = meta_io.load_workspace(ws_yaml)
    ws_root = ws_data.get("workspace") or {}
    ws_intent = ws_data.get("intent") or {}

    meetings = meta_io.scan_meetings(root)

    active = _resolve_active(root, meetings, active_dir)

    view = {
        "workspace": {
            "name": ws_root.get("name", root.name),
            "root_path": str(root).replace("\\", "/"),
            "scanned_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "scenario": ws_root.get("scenario", ""),
        },
        "intent": {
            "goal": ws_intent.get("goal", ""),
            "deliverables": list(ws_intent.get("deliverables") or []),
        },
        "meetings": meetings,
        "active": active,
    }
    return view


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aggregate.py",
        description="构造 mint 工作区 workspace-view 内存聚合对象",
    )
    parser.add_argument("--ws", required=True, help="工作区根路径")
    parser.add_argument("--active", default=None, help="可选显式 active 会议目录名")
    args = parser.parse_args(argv)
    try:
        view = build_workspace_view(args.ws, args.active)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps(view, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
