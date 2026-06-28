#!/usr/bin/env python
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""一次性升级脚本：将老 mint 工作区迁移到 .mint/ + 新 meta.yaml schema.

用法：
    uv run --script upgrade_workspace.py <工作区根目录> \\
        --scenario interview \\
        --goal "项目目标一句话" \\
        --deliverables "观点分析,校对稿,结构化脱敏稿"

幂等：重复跑不会破坏已迁移的数据（已有 .mint/ 时报错退出）。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


STAGE_ORDER = ["transcribe", "refine", "polish", "extract"]


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )


def infer_cursor_and_last_action(meta: dict) -> tuple[str, str]:
    """从 stages 的 completed 情况和 revisions 推断 cursor 与 last_action."""
    stages = meta.get("stages") or {}
    cursor = "transcribe"
    for name in STAGE_ORDER:
        st = stages.get(name) or {}
        if st.get("status") == "completed":
            cursor = name

    timestamps: list[str] = []
    for name in STAGE_ORDER:
        st = stages.get(name) or {}
        ts = st.get("completed_at")
        if ts:
            timestamps.append(str(ts))
    for rev in meta.get("revisions") or []:
        ts = rev.get("timestamp")
        if ts:
            timestamps.append(str(ts))

    last_action = max(timestamps) if timestamps else datetime.now().isoformat(timespec="seconds")
    return cursor, last_action


def upgrade_meta(meta: dict) -> dict:
    """为老 meta.yaml 补齐 intent / current / next_hints 三块.

    已有字段全部保留，按 PRD 8.1 顺序重组输出。
    """
    project = meta.get("project", "")
    created = meta.get("created", "")
    source_audio = meta.get("source_audio", "")
    stages = meta.get("stages") or {}
    revisions = meta.get("revisions") or []
    desensitization = meta.get("desensitization") or {}

    cursor, last_action = infer_cursor_and_last_action(meta)
    all_completed = all(
        (stages.get(n) or {}).get("status") == "completed" for n in STAGE_ORDER
    )

    intent = meta.get("intent") or {
        "goal": "",
        "deliverables": [],
        "skip_stages": [],
        "scenario": "",
    }

    current = meta.get("current") or {
        "cursor": cursor,
        "last_action": last_action,
        "last_action_desc": "迁移升级" if not all_completed else "全部阶段已完成",
        "blockers": [],
    }

    next_hints = meta.get("next_hints") or {
        "primary": {
            "cmd": f"/mint:status {project}" if all_completed else f"/mint:next {project}",
            "reason": "全部阶段已完成，查看最终产出快照" if all_completed else "升级后重新评估下一步",
        },
        "alternatives": [],
    }

    return {
        "project": project,
        "created": created,
        "source_audio": source_audio,
        "stages": stages,
        "revisions": revisions,
        "desensitization": desensitization,
        "intent": intent,
        "current": current,
        "next_hints": next_hints,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("workspace_root", help="工作区根目录")
    p.add_argument("--scenario", required=True, choices=["interview", "meeting"])
    p.add_argument("--goal", required=True, help="工作区整体目标（一句话）")
    p.add_argument(
        "--deliverables", required=True,
        help="期望交付物清单，逗号分隔",
    )
    p.add_argument("--dry-run", action="store_true", help="只打印将要做什么，不实际写入")
    args = p.parse_args()

    ws = Path(args.workspace_root)
    if not ws.exists():
        print(f"FAIL: 工作区目录不存在 {ws}", file=sys.stderr)
        return 2

    mint_dir = ws / ".mint"
    if mint_dir.exists():
        print(f"FAIL: .mint/ 已存在，拒绝覆盖 {mint_dir}", file=sys.stderr)
        return 3

    # 扫描会议子目录（含 meta.yaml 的一级子目录）
    meetings: list[Path] = []
    for child in sorted(ws.iterdir()):
        if not child.is_dir():
            continue
        if (child / "meta.yaml").is_file():
            meetings.append(child)

    print(f"发现 {len(meetings)} 个会议：{[m.name for m in meetings]}")

    deliverables = [x.strip() for x in args.deliverables.split(",") if x.strip()]

    workspace_yaml_content = {
        "workspace": {
            "name": ws.name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "scenario": args.scenario,
        },
        "intent": {
            "goal": args.goal,
            "deliverables": deliverables,
        },
    }

    # 来源 registry
    src_registry = ws / "desensitization_registry.yaml"
    has_registry = src_registry.is_file()

    if args.dry_run:
        print("--- DRY RUN ---")
        print(f"将创建 {mint_dir}/workspace.yaml:")
        print(yaml.safe_dump(workspace_yaml_content, allow_unicode=True, sort_keys=False))
        if has_registry:
            print(f"将移动 {src_registry} -> {mint_dir}/desensitization_registry.yaml")
        print(f"将补齐 {len(meetings)} 个 meta.yaml 的 intent/current/next_hints")
        return 0

    # 执行
    mint_dir.mkdir()
    _dump_yaml(mint_dir / "workspace.yaml", workspace_yaml_content)
    print(f"OK: created {mint_dir}/workspace.yaml")

    if has_registry:
        dst_registry = mint_dir / "desensitization_registry.yaml"
        shutil.move(str(src_registry), str(dst_registry))
        print(f"OK: moved registry -> {dst_registry}")

    for m in meetings:
        meta_path = m / "meta.yaml"
        meta = _load_yaml(meta_path)
        new_meta = upgrade_meta(meta)
        _dump_yaml(meta_path, new_meta)
        print(f"OK: upgraded {meta_path}")

    print(f"完成：{len(meetings)} 个会议 meta.yaml 已补齐新字段")
    return 0


if __name__ == "__main__":
    sys.exit(main())
