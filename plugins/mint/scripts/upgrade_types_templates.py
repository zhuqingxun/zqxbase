#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6.0"]
# ///
"""存量迁移脚本：为已 init 的 interview 工作区补齐 types + templates 两块。

用法:
    uv run --script upgrade_types_templates.py <workspace_root> \
        --types "id1=name1,id2=name2" \
        --templates "id1=name1=file1=applies_to1|id2=name2=file2=applies_to2" \
        [--dry-run] [--sanitize]

参数约定:
    --types       逗号分隔的 id=name 对
    --templates   "|" 分隔多 template；每个 template 内用 "=" 分隔四字段：
                  id=name=file=applies_to
                  applies_to 多个值用 ":" 分隔（避免与外层 "|" 和内层 "=" 冲突）
    --dry-run     仅打印计划的 yaml 变更 + mv 操作，不实际执行
    --sanitize    把 PDF 重命名为 <tpl-id>.<ext> 进入 .mint/templates/
                  默认保留原文件名（PRD 8.3 允许；中文名在 Windows pathlib 下可用）

幂等保护:
    已存在非空 interviewee_types[] 或 templates[] 块 → 报错退出（不覆盖用户数据）
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml


WORKSPACE_FIELD_ORDER = ["workspace", "intent", "interviewee_types", "templates"]
TYPE_FIELD_ORDER = ["id", "name", "default_template_id"]
TEMPLATE_FIELD_ORDER = ["id", "name", "file", "applies_to"]


def _reorder_dict(data: dict, order: list[str]) -> dict:
    out = {}
    for k in order:
        if k in data:
            out[k] = data[k]
    for k in data:
        if k not in out:
            out[k] = data[k]
    return out


def _load_workspace(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"workspace.yaml 不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_workspace(path: Path, ws: dict) -> None:
    ordered = _reorder_dict(ws, WORKSPACE_FIELD_ORDER)
    if "workspace" in ordered and isinstance(ordered["workspace"], dict):
        ordered["workspace"] = _reorder_dict(
            ordered["workspace"], ["name", "created_at", "scenario"]
        )
    if "intent" in ordered and isinstance(ordered["intent"], dict):
        ordered["intent"] = _reorder_dict(
            ordered["intent"], ["goal", "deliverables"]
        )
    if "interviewee_types" in ordered and isinstance(ordered["interviewee_types"], list):
        ordered["interviewee_types"] = [
            _reorder_dict(t, TYPE_FIELD_ORDER) if isinstance(t, dict) else t
            for t in ordered["interviewee_types"]
        ]
    if "templates" in ordered and isinstance(ordered["templates"], list):
        ordered["templates"] = [
            _reorder_dict(t, TEMPLATE_FIELD_ORDER) if isinstance(t, dict) else t
            for t in ordered["templates"]
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            ordered,
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )


def _parse_types_arg(s: str) -> list[dict[str, Any]]:
    """解析 --types "id1=name1,id2=name2" """
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in s.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(f"--types 片段格式错误，应为 id=name: {chunk}")
        tid, name = chunk.split("=", 1)
        tid = tid.strip()
        name = name.strip()
        if not tid or not name:
            raise ValueError(f"--types 片段 id 或 name 为空: {chunk}")
        if tid in seen:
            raise ValueError(f"--types 中出现重复 id: {tid}")
        seen.add(tid)
        items.append({
            "id": tid,
            "name": name,
            "default_template_id": None,
        })
    if not items:
        raise ValueError("--types 为空，至少提供一个 id=name 对")
    return items


def _parse_templates_arg(s: str) -> list[dict[str, Any]]:
    """解析 --templates "id=name=file=applies_to[|id=name=file=applies_to]"

    applies_to 多个值用 ":" 分隔。
    """
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in s.split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("=")
        if len(parts) != 4:
            raise ValueError(
                f"--templates 片段格式错误，应为 id=name=file=applies_to: {chunk}"
            )
        tid, name, file, applies_to_raw = (p.strip() for p in parts)
        if not tid or not name or not file or not applies_to_raw:
            raise ValueError(f"--templates 片段存在空字段: {chunk}")
        if tid in seen:
            raise ValueError(f"--templates 中出现重复 id: {tid}")
        seen.add(tid)
        applies_to = [a.strip() for a in applies_to_raw.split(":") if a.strip()]
        if not applies_to:
            raise ValueError(f"--templates 片段 applies_to 为空: {chunk}")
        items.append({
            "id": tid,
            "name": name,
            "file": file,
            "applies_to": applies_to,
        })
    if not items:
        raise ValueError("--templates 为空，至少提供一个 template 定义")
    return items


def _resolve_source_file(root: Path, file_arg: str) -> Path:
    """把 --templates 里的 file 字段解析为源 PDF 的绝对路径。

    支持：
    - 绝对路径（存在 → 返回）
    - 相对工作区根的路径（如 "internal.pdf" 或 ".mint/templates/foo.pdf" → root/该路径）
    """
    p = Path(file_arg)
    if p.is_absolute():
        return p
    return (root / file_arg).resolve()


def _compute_target_file(
    root: Path, tpl_id: str, src: Path, sanitize: bool
) -> tuple[Path, str]:
    """返回 (目标绝对路径, workspace.yaml 里存的相对路径)"""
    target_dir = root / ".mint" / "templates"
    if sanitize:
        ext = src.suffix or ".pdf"
        target = target_dir / f"{tpl_id}{ext}"
    else:
        target = target_dir / src.name
    rel = target.relative_to(root).as_posix()
    return target, rel


def _backfill_default_templates(
    types: list[dict[str, Any]], templates: list[dict[str, Any]]
) -> None:
    """对每个 template 的 applies_to 里的 type，若 default 为 null 则回填该 template.id。

    多匹配取第一个（保持输入顺序）。直接在 types list 上原地修改。
    """
    type_index: dict[str, dict[str, Any]] = {t["id"]: t for t in types}
    for tpl in templates:
        for tid in tpl["applies_to"]:
            t = type_index.get(tid)
            if t is None:
                raise ValueError(
                    f"template {tpl['id']} 的 applies_to 含未注册的 type id: {tid}"
                )
            if t.get("default_template_id") is None:
                t["default_template_id"] = tpl["id"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("workspace_root", help="工作区根目录")
    ap.add_argument("--types", required=True, help="逗号分隔的 id=name")
    ap.add_argument(
        "--templates",
        required=True,
        help="'|' 分隔多 template；每条 id=name=file=applies_to（applies_to 多值用 ':' 分隔）",
    )
    ap.add_argument("--dry-run", action="store_true", help="仅打印计划，不执行")
    ap.add_argument(
        "--sanitize",
        action="store_true",
        help="把 PDF 重命名为 <tpl-id>.<ext>（默认保留原文件名）",
    )
    args = ap.parse_args()

    root = Path(args.workspace_root).resolve()
    ws_path = root / ".mint" / "workspace.yaml"

    if not ws_path.is_file():
        print(
            f"ERROR: 工作区未初始化（缺少 {ws_path}），请先运行 /mint:init",
            file=sys.stderr,
        )
        return 2

    ws = _load_workspace(ws_path)
    scenario = ((ws.get("workspace") or {}).get("scenario"))
    if scenario != "interview":
        print(
            f"ERROR: types/templates 迁移仅支持 interview 场景（当前 scenario={scenario!r}）",
            file=sys.stderr,
        )
        return 2

    existing_types = ws.get("interviewee_types") or []
    existing_templates = ws.get("templates") or []
    if existing_types or existing_templates:
        print(
            "ERROR: 已升级过（workspace.yaml 已含非空 interviewee_types 或 templates 块），"
            "如需重跑请先手工清空这两个块",
            file=sys.stderr,
        )
        return 2

    try:
        types = _parse_types_arg(args.types)
        templates = _parse_templates_arg(args.templates)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    type_ids = {t["id"] for t in types}
    for tpl in templates:
        unknown = [a for a in tpl["applies_to"] if a not in type_ids]
        if unknown:
            print(
                f"ERROR: template {tpl['id']} 的 applies_to 含未注册的 type: {','.join(unknown)}",
                file=sys.stderr,
            )
            return 2

    mv_plan: list[tuple[Path, Path, str]] = []
    for tpl in templates:
        src = _resolve_source_file(root, tpl["file"])
        if not src.exists():
            print(
                f"ERROR: template {tpl['id']} 的源文件不存在: {src}",
                file=sys.stderr,
            )
            return 2
        target, rel = _compute_target_file(root, tpl["id"], src, args.sanitize)
        tpl["file"] = rel
        mv_plan.append((src, target, tpl["id"]))

    _backfill_default_templates(types, templates)

    ws_new = dict(ws)
    ws_new["interviewee_types"] = types
    ws_new["templates"] = templates

    if args.dry_run:
        print("DRY-RUN: 计划的变更如下（未实际执行）")
        print("--- mv 清单 ---")
        for src, target, tid in mv_plan:
            print(f"  [{tid}] {src}  ->  {target}")
        print("--- workspace.yaml 新增块 ---")
        preview = {
            "interviewee_types": types,
            "templates": templates,
        }
        print(yaml.safe_dump(preview, allow_unicode=True, sort_keys=False))
        return 0

    (root / ".mint" / "templates").mkdir(parents=True, exist_ok=True)
    moved: list[tuple[Path, Path]] = []
    for src, target, tid in mv_plan:
        if target.exists():
            print(
                f"ERROR: 目标文件已存在 {target}（template {tid}）。已 mv 操作: {moved}",
                file=sys.stderr,
            )
            return 2
        try:
            shutil.move(str(src), str(target))
            moved.append((src, target))
            print(f"OK: moved [{tid}] -> {target}")
        except Exception as e:
            print(
                f"ERROR: mv 失败 [{tid}] {src} -> {target}: {e}\n"
                f"已完成的 mv（需手工回滚）: {moved}",
                file=sys.stderr,
            )
            return 2

    try:
        _save_workspace(ws_path, ws_new)
        print(f"OK: updated {ws_path}")
    except Exception as e:
        print(
            f"ERROR: 写入 workspace.yaml 失败: {e}\n"
            f"注意：PDF 已移动至 .mint/templates/，workspace.yaml 未更新，"
            f"请手工编辑或回滚 mv 操作",
            file=sys.stderr,
        )
        return 2

    print(
        f"完成：注册 {len(types)} 个 type、{len(templates)} 个 template，"
        f"mv {len(moved)} 个文件"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
