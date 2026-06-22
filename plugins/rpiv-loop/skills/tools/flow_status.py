#!/usr/bin/env python3
"""rpiv-loop:flow-status 纯程序实现。

正常 5 个 mode (默认 / all / <status> / <feature> / check) 全程 Python。
fix mode 在 stdout 末尾输出 __NEED_LLM__\\n<json payload> 标记,
让 SKILL 接管 AskUserQuestion 流程处理用户决策项。

零依赖：仅 stdlib 正则解析 frontmatter,与 tools/check_acceptance.py 保持一致。

退出码:
  0  正常输出
  1  用户参数错误 / feature 不存在
  2  内部错误（IO、解析失败 等致命）
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

# ----- 合法 status（沿用 hooks/validate_rpiv_status.py 实现，非 spec.md）-----
LEGAL_STATUS = {
    "process": {"pending", "in-progress", "completed", "superseded", "archived"},
    "todo": {"open", "in-progress", "completed", "archived"},
    "aux": {"pending", "completed", "archived"},
}

# ----- 文件名前缀映射（前缀 -> phase 显示名）-----
PROCESS_PREFIXES = [
    ("prd-", "PRD"),
    ("plan-", "Plan"),
    ("code-review-", "Code Review"),
    ("exec-report-", "Exec Report"),
    ("system-review-", "System Review"),  # 历史兼容：system-review 命令已删除，保留以识别旧文件
    ("delivery-report-", "Delivery"),
    ("test-strategy-", "Test Strategy"),
    ("test-specs-", "Test Specs"),
    ("alignment-review-", "Alignment"),
    ("code-audit-", "Code Audit"),
    ("handoff-", "Handoff"),
]
AUX_PREFIXES = [
    ("brainstorm-summary-", "Brainstorm"),
    ("research-", "Research"),
]
TODO_PREFIXES = [
    ("issue-", "Issue"),
    ("feature-", "Feature"),
    ("fix-", "Fix"),
    ("todo-", "Todo"),
]

# 精简摘要里 completed 区块展示这几个 phase 的 ✓/-
SUMMARY_PHASES = ["PRD", "Plan", "Code Review", "Exec Report", "Delivery"]

# all 表格展示的 phase（精简版 6 个）
ALL_TABLE_PHASES = ["PRD", "Plan", "Code Review", "Exec Report", "System Review", "Delivery"]

# 状态符号
STATUS_SYMBOL = {
    "pending": "⏳",
    "in-progress": "🔄",
    "completed": "✓",
    "superseded": "⏪",
    "archived": "📦",
    "open": "🔓",
}

# fix 模式残留项的 LLM 执行协议(运行时下发,SKILL.md 不重复维护)
PROTOCOL_INSTRUCTIONS = """PROTOCOL:
按下列步骤处理 items(payload 见上方 JSON 行):

1. 用 AskUserQuestion 把 items 包装成选项。kind → 选项映射:
   - stale_in_progress → ["改为 completed", "回退到 pending", "保持 in-progress 并更新 updated_at"]
   - illegal_status → 把 legal_options 各值列为选项
   - superseded_missing_by → 让用户提供 superseded_by 路径(无合适选项时让用户填)
   - brainstorm_no_prd → ["创建 PRD 推进", "标记 brainstorm 为 completed (放弃推进)", "保持 pending"]
   - validation_without_plan / exec_report_before_plan_done → 让用户决定补 Plan 还是回退 validation
   - completed_todo_unarchived → **不询问用户**,直接复述 item 的 command_hint 字段(如 /rpiv-loop:archive rpiv/todo/xxx.md),告诉用户跑该命令即可
2. 每个 item 一组问题,4 个以内同批问;超过分批。
3. 拿到用户决策后,用 Edit 工具直接改对应文件的 frontmatter(status / superseded_by / updated_at,**必须同步 updated_at = 当前时间 ISO 8601**)。
4. 全部处理完后,重跑 `uv run --no-project python D:/CODE/plugins/rpiv-loop/tools/flow_status.py check` 确认无残留异常,输出最终 check 结果。
"""

# ----- frontmatter 解析 -----
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
SCALAR_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*$", re.MULTILINE)


def _strip_value(raw: str) -> str:
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        v = v[1:-1]
    return v


def parse_frontmatter(text: str) -> dict | None:
    """返回 frontmatter 字段 dict；无 frontmatter 返回 None。

    仅解析单行 scalar 字段（status / type / title / description / created_at /
    updated_at / archived_at / priority / superseded_by / superseded_by_note）。
    多行 list 字段（related_files）取所有 `- ...` 行的字面值。
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    block = m.group(1)
    fields: dict = {}
    for fm in SCALAR_RE.finditer(block):
        key = fm.group(1)
        raw = fm.group(2)
        if raw == "":
            fields[key] = None
        else:
            fields[key] = _strip_value(raw)

    related: list[str] = []
    in_related = False
    for line in block.splitlines():
        if line.startswith("related_files:"):
            in_related = True
            continue
        if in_related:
            stripped = line.lstrip()
            if stripped.startswith("- "):
                related.append(_strip_value(stripped[2:]))
            elif line and not line.startswith(" ") and not line.startswith("\t"):
                in_related = False
    if related:
        fields["related_files"] = related
    return fields


# ----- 文件分类 -----
def classify_file(rel_posix: str, filename: str) -> str:
    """返回 'process' | 'todo' | 'aux'."""
    if "rpiv/todo/" in rel_posix:
        return "todo"
    for prefix, _ in AUX_PREFIXES:
        if filename.startswith(prefix):
            return "aux"
    return "process"


def parse_filename(category: str, filename: str) -> tuple[str, str]:
    """返回 (phase 显示名, feature 名)。无法识别时 phase='Unknown'."""
    stem = filename[:-3] if filename.endswith(".md") else filename
    if category == "todo":
        for prefix, label in TODO_PREFIXES:
            if stem.startswith(prefix):
                return label, stem[len(prefix):]
        return "Todo", stem
    if category == "aux":
        for prefix, label in AUX_PREFIXES:
            if stem.startswith(prefix):
                return label, stem[len(prefix):]
    for prefix, label in PROCESS_PREFIXES:
        if stem.startswith(prefix):
            return label, stem[len(prefix):]
    return "Unknown", stem


# ----- 扫描 -----
def scan_rpiv(rpiv_dir: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """扫描 rpiv 下所有 md，返回 (live_files, archived_files, parse_errors).

    live_files: rpiv/{requirements,plans,validation,todo}/*.md + rpiv/{brainstorm-summary-*,research-*,handoff-*}.md
    archived_files: rpiv/archive/*.md
    parse_errors: 文件存在但 frontmatter 解析失败 / 缺失
    """
    live: list[dict] = []
    archived: list[dict] = []
    errors: list[dict] = []

    subdirs = ["requirements", "plans", "validation", "todo"]
    candidates: list[Path] = []
    for sub in subdirs:
        d = rpiv_dir / sub
        if d.is_dir():
            candidates.extend(p for p in d.iterdir() if p.is_file() and p.suffix == ".md")
    # rpiv 根级 aux + handoff
    for p in rpiv_dir.iterdir():
        if p.is_file() and p.suffix == ".md":
            name = p.name
            if any(name.startswith(prefix) for prefix, _ in AUX_PREFIXES) or name.startswith("handoff-"):
                candidates.append(p)

    for p in candidates:
        rel_posix = p.relative_to(rpiv_dir.parent).as_posix()
        category = classify_file(rel_posix, p.name)
        phase, feature = parse_filename(category, p.name)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append({"path": rel_posix, "error": f"IO: {exc}"})
            continue
        fm = parse_frontmatter(text)
        if fm is None:
            errors.append({"path": rel_posix, "error": "无 frontmatter"})
            continue
        live.append({
            "path": rel_posix,
            "abs_path": str(p),
            "filename": p.name,
            "category": category,
            "phase": phase,
            "feature": feature,
            "fm": fm,
        })

    archive_dir = rpiv_dir / "archive"
    if archive_dir.is_dir():
        for p in archive_dir.iterdir():
            if p.is_file() and p.suffix == ".md":
                rel_posix = p.relative_to(rpiv_dir.parent).as_posix()
                category = classify_file(rel_posix, p.name)
                # archive 里 todo 也归 todo,其余按文件名识别
                if "/archive/" in rel_posix:
                    # 不能从路径判断 todo,改用文件名前缀
                    if any(p.name.startswith(prefix) for prefix, _ in TODO_PREFIXES):
                        category = "todo"
                    elif any(p.name.startswith(prefix) for prefix, _ in AUX_PREFIXES):
                        category = "aux"
                    else:
                        category = "process"
                phase, feature = parse_filename(category, p.name)
                try:
                    text = p.read_text(encoding="utf-8")
                except OSError:
                    archived.append({
                        "path": rel_posix, "filename": p.name, "category": category,
                        "phase": phase, "feature": feature, "fm": {},
                    })
                    continue
                fm = parse_frontmatter(text) or {}
                archived.append({
                    "path": rel_posix, "abs_path": str(p), "filename": p.name,
                    "category": category, "phase": phase, "feature": feature, "fm": fm,
                })

    return live, archived, errors


# ----- 一致性检查 -----
def _parse_ts(s: str | None) -> datetime.datetime | None:
    if not s:
        return None
    s = s.strip().strip("\"'")
    # 兼容带/不带时区后缀
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def consistency_check(live: list[dict]) -> list[dict]:
    """返回异常项列表，每项含 path / kind / message / fixable / suggested_action."""
    anomalies: list[dict] = []

    by_feature: dict[str, dict[str, dict]] = {}
    for f in live:
        if f["category"] != "process" or f["phase"] == "Unknown":
            continue
        by_feature.setdefault(f["feature"], {})[f["phase"]] = f

    # 1. status 合法性
    for f in live:
        status = (f["fm"].get("status") or "").strip()
        legal = LEGAL_STATUS.get(f["category"], set())
        if status and status not in legal:
            anomalies.append({
                "path": f["path"],
                "kind": "illegal_status",
                "message": f"status={status!r} 不在合法枚举 {sorted(legal)}",
                "fixable": False,
                "suggested_action": "ask_user_for_legal_status",
                "current_status": status,
                "legal_options": sorted(legal),
            })

    # 2. superseded 但缺 superseded_by
    for f in live:
        if (f["fm"].get("status") or "") == "superseded" and not f["fm"].get("superseded_by"):
            anomalies.append({
                "path": f["path"],
                "kind": "superseded_missing_by",
                "message": "status=superseded 但缺 superseded_by 字段",
                "fixable": False,
                "suggested_action": "ask_user_for_superseded_by",
            })

    # 3. Plan completed/in-progress 但关联 PRD 不是 completed
    for feature, phases in by_feature.items():
        prd = phases.get("PRD")
        plan = phases.get("Plan")
        if plan and prd:
            plan_status = (plan["fm"].get("status") or "").strip()
            prd_status = (prd["fm"].get("status") or "").strip()
            if plan_status in ("completed", "in-progress") and prd_status != "completed":
                anomalies.append({
                    "path": prd["path"],
                    "kind": "prd_behind_plan",
                    "message": f"Plan 为 {plan_status} 但 PRD 仍为 {prd_status}",
                    "fixable": True,
                    "suggested_action": "auto_update_prd_to_completed",
                    "feature": feature,
                })

    # 4. Validation 文件 completed 但 Plan 不是 completed
    validation_phases = {"Code Review", "Exec Report", "System Review", "Delivery", "Alignment"}
    for feature, phases in by_feature.items():
        plan = phases.get("Plan")
        for vp in validation_phases:
            v = phases.get(vp)
            if v and (v["fm"].get("status") or "") == "completed":
                if not plan:
                    anomalies.append({
                        "path": v["path"],
                        "kind": "validation_without_plan",
                        "message": f"{vp} 为 completed 但找不到对应 Plan",
                        "fixable": False,
                        "suggested_action": "ask_user_to_locate_plan",
                        "feature": feature,
                    })
                elif (plan["fm"].get("status") or "") != "completed":
                    anomalies.append({
                        "path": plan["path"],
                        "kind": "plan_behind_validation",
                        "message": f"{vp} 已 completed 但 Plan 仍为 {plan['fm'].get('status') or '空'}",
                        "fixable": True,
                        "suggested_action": "auto_update_plan_to_completed",
                        "feature": feature,
                    })

    # 5. in-progress 超过 48 小时
    now = datetime.datetime.now()
    cutoff = datetime.timedelta(hours=48)
    for f in live:
        status = (f["fm"].get("status") or "").strip()
        if status == "in-progress":
            updated = _parse_ts(f["fm"].get("updated_at"))
            if updated and updated.tzinfo is None and now - updated > cutoff:
                anomalies.append({
                    "path": f["path"],
                    "kind": "stale_in_progress",
                    "message": f"in-progress 已超 48h（updated_at={f['fm'].get('updated_at')}）",
                    "fixable": False,
                    "suggested_action": "ask_user_to_advance_or_rollback",
                    "hours_stale": int((now - updated).total_seconds() / 3600),
                })

    # 6. todo status=completed 但还在 todo/ 中（应归档,需用户调 archive skill）
    for f in live:
        if f["category"] == "todo" and (f["fm"].get("status") or "") == "completed":
            anomalies.append({
                "path": f["path"],
                "kind": "completed_todo_unarchived",
                "message": "todo 已 completed 但未归档",
                "fixable": False,
                "suggested_action": "run_archive_command",
                "command_hint": f"/rpiv-loop:archive {f['path']}",
            })

    # 7. todo status=superseded（hook 不接受）
    for f in live:
        if f["category"] == "todo" and (f["fm"].get("status") or "") == "superseded":
            anomalies.append({
                "path": f["path"],
                "kind": "todo_superseded_disallowed",
                "message": "todo 不支持 superseded（hook 限制），应改为 archived 并保留 superseded_by 字段",
                "fixable": True,
                "suggested_action": "auto_change_todo_superseded_to_archived",
            })

    # 8. brainstorm-summary 存在但无对应 PRD
    aux_brainstorms = {f["feature"]: f for f in live if f["phase"] == "Brainstorm"}
    for feature, bs in aux_brainstorms.items():
        if (bs["fm"].get("status") or "") in ("pending", "in-progress"):
            phases = by_feature.get(feature, {})
            if "PRD" not in phases:
                anomalies.append({
                    "path": bs["path"],
                    "kind": "brainstorm_no_prd",
                    "message": "brainstorm-summary 存在但未推进到 PRD",
                    "fixable": False,
                    "suggested_action": "remind_user",
                })

    # 9. exec-report 存在但 Plan 不是 completed
    for feature, phases in by_feature.items():
        er = phases.get("Exec Report")
        plan = phases.get("Plan")
        if er and plan:
            plan_status = (plan["fm"].get("status") or "").strip()
            if plan_status != "completed":
                anomalies.append({
                    "path": er["path"],
                    "kind": "exec_report_before_plan_done",
                    "message": f"exec-report 已存在但 Plan 仍为 {plan_status or '空'}",
                    "fixable": False,
                    "suggested_action": "manual_review",
                    "feature": feature,
                })

    return anomalies


# ----- 输出格式化辅助 -----
def _fmt_ts(s: str | None) -> str:
    if not s:
        return "—"
    ts = _parse_ts(s)
    if ts:
        return ts.strftime("%m-%d %H:%M")
    return s[:16]


def _short_desc(fm: dict) -> str:
    return fm.get("title") or fm.get("description") or ""


# ----- mode: 精简摘要 -----
def mode_summary(live: list[dict], archived: list[dict], errors: list[dict]) -> int:
    anomalies = consistency_check(live)

    process_files = [f for f in live if f["category"] == "process"]
    todo_files = [f for f in live if f["category"] == "todo"]
    aux_files = [f for f in live if f["category"] == "aux"]

    n_in_progress = sum(1 for f in process_files if (f["fm"].get("status") or "") == "in-progress")
    n_pending = sum(1 for f in process_files if (f["fm"].get("status") or "") == "pending")
    n_completed = sum(1 for f in process_files if (f["fm"].get("status") or "") == "completed")

    todo_open = sum(1 for f in todo_files if (f["fm"].get("status") or "") == "open")
    todo_in_prog = sum(1 for f in todo_files if (f["fm"].get("status") or "") == "in-progress")
    todo_done = sum(1 for f in todo_files if (f["fm"].get("status") or "") == "completed")

    print("## 流程状态\n")
    parts = [f"⚠️ 异常 {len(anomalies)}" if anomalies else "",
             f"🔄 进行中 {n_in_progress}",
             f"⏳ 待处理 {n_pending}",
             f"✓ 已完成 {n_completed}",
             f"📦 已归档 {len(archived)}",
             f"📋 Todo {len(todo_files)}"]
    print(" | ".join(p for p in parts if p))
    print()

    if errors:
        print(f"### ❓ 解析失败（{len(errors)} 个）\n")
        for e in errors:
            print(f"- {e['path']} — {e['error']}")
        print()

    if anomalies:
        print(f"### ⚠️ 异常（{len(anomalies)} 项）\n")
        for a in anomalies:
            print(f"- `{a['path']}` — {a['message']}")
        print(f"\n→ 修复建议：`/rpiv-loop:flow-status fix`\n")

    in_prog = [f for f in process_files if (f["fm"].get("status") or "") == "in-progress"]
    if in_prog:
        print("### 🔄 进行中\n")
        for f in in_prog:
            desc = _short_desc(f["fm"])
            print(f"- {f['filename']} — {desc} [{f['phase']}]")
        print()

    pending = [f for f in process_files if (f["fm"].get("status") or "") == "pending"]
    if pending:
        print("### ⏳ 待处理\n")
        for f in pending:
            desc = _short_desc(f["fm"])
            print(f"- {f['filename']} — {desc} [{f['phase']}]")
        print()

    # 已完成：按 feature 聚合
    completed_by_feature: dict[str, dict[str, dict]] = {}
    for f in process_files:
        if (f["fm"].get("status") or "") == "completed":
            completed_by_feature.setdefault(f["feature"], {})[f["phase"]] = f
    if completed_by_feature:
        print("### ✓ 已完成（建议归档 → `/rpiv-loop:archive all`）\n")
        for feature, phases in sorted(completed_by_feature.items()):
            tags = " ".join(f"{p} ✓" for p in SUMMARY_PHASES if p in phases)
            extras = [p for p in phases if p not in SUMMARY_PHASES]
            if extras:
                tags += " " + " ".join(f"{p} ✓" for p in extras)
            print(f"- {feature} — {tags}")
        print()

    if todo_files:
        print(f"### 📋 Todo (open: {todo_open} | in-progress: {todo_in_prog} | completed: {todo_done})\n")
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        priority_icon = {"high": "🔴 high", "medium": "🟡 medium", "low": "🔵 low"}
        type_icon = {"feature": "✨", "todo": "📝", "issue": "🐛", "fix": "🔧"}
        status_icon = {"open": "🔓 open", "in-progress": "🔄 in-progress",
                       "completed": "✓ completed", "archived": "📦 archived"}

        def _todo_sort_key(f: dict) -> tuple:
            pri = (f["fm"].get("priority") or "").lower()
            typ = f["fm"].get("type") or ""
            return (priority_rank.get(pri, 99), typ, f["feature"])

        print("| 优先级 | 类型 | 状态 | 标识 | 标题 |")
        print("|--------|------|------|------|------|")
        for f in sorted(todo_files, key=_todo_sort_key):
            pri = (f["fm"].get("priority") or "").lower()
            pri_disp = priority_icon.get(pri, "—")
            typ = f["fm"].get("type") or ""
            typ_disp = f"{type_icon.get(typ, '📌')} {typ}" if typ else "—"
            status = f["fm"].get("status") or "?"
            st_disp = status_icon.get(status, status)
            title = _short_desc(f["fm"]).replace("|", r"\|")
            print(f"| {pri_disp} | {typ_disp} | {st_disp} | {f['feature']} | {title} |")
        print()

    if aux_files:
        print("### 📝 辅助文件\n")
        for f in aux_files:
            status = f["fm"].get("status") or "?"
            desc = _short_desc(f["fm"])
            print(f"- [{status}] {f['filename']} — {desc}")
        print()

    if archived:
        archived_features = {f["feature"] for f in archived}
        print(f"### 📦 已归档（{len(archived)} 个文件, {len(archived_features)} 个特性, 详情见 `/rpiv-loop:flow-status all`）\n")

    return 0


# ----- mode: all (完整表格) -----
def mode_all(live: list[dict], archived: list[dict], errors: list[dict]) -> int:
    process_files = [f for f in live if f["category"] == "process"]
    by_feature: dict[str, dict[str, dict]] = {}
    for f in process_files:
        by_feature.setdefault(f["feature"], {})[f["phase"]] = f

    print("## 全部特性状态\n")
    header = "| 特性 | " + " | ".join(ALL_TABLE_PHASES) + " | 状态 |"
    sep = "|------|" + "|".join(["-----"] * len(ALL_TABLE_PHASES)) + "|------|"
    print(header)
    print(sep)
    for feature in sorted(by_feature.keys()):
        phases = by_feature[feature]
        cells = []
        all_statuses = []
        for p in ALL_TABLE_PHASES:
            f = phases.get(p)
            if not f:
                cells.append("—")
            else:
                st = (f["fm"].get("status") or "").strip()
                all_statuses.append(st)
                cells.append(STATUS_SYMBOL.get(st, "?"))
        if all_statuses and all(s == "completed" for s in all_statuses):
            overall = "可归档"
        elif "in-progress" in all_statuses:
            overall = "进行中"
        elif "pending" in all_statuses:
            overall = "待处理"
        else:
            overall = "—"
        print(f"| {feature} | " + " | ".join(cells) + f" | {overall} |")
    print()

    if archived:
        archived_by_feature: dict[str, list[str]] = {}
        for f in archived:
            archived_by_feature.setdefault(f["feature"], []).append(f["phase"])
        print(f"📦 已归档（{len(archived_by_feature)} 个特性）:\n")
        for feature, phases in sorted(archived_by_feature.items()):
            print(f"- {feature}: {', '.join(sorted(set(phases)))}")
        print()

    todo_files = [f for f in live if f["category"] == "todo"]
    if todo_files:
        print(f"📋 Todo ({len(todo_files)} 项):\n")
        for f in todo_files:
            status = f["fm"].get("status") or "?"
            desc = _short_desc(f["fm"])
            print(f"- [{status}] {f['phase']}: {f['feature']} — {desc}")
        print()

    if errors:
        print(f"❓ 解析失败 ({len(errors)}):\n")
        for e in errors:
            print(f"- {e['path']} — {e['error']}")
        print()

    return 0


# ----- mode: 按状态过滤 -----
def mode_filter(live: list[dict], target_status: str) -> int:
    matched = [f for f in live if (f["fm"].get("status") or "") == target_status]
    icon = STATUS_SYMBOL.get(target_status, "")
    print(f"## {icon} {target_status} ({len(matched)} 个)\n")
    if not matched:
        print("无匹配文件。")
        return 0
    for f in sorted(matched, key=lambda x: x["fm"].get("updated_at") or "", reverse=True):
        desc = _short_desc(f["fm"])
        updated = _fmt_ts(f["fm"].get("updated_at"))
        print(f"- {f['filename']} → {f['path']}")
        print(f"  [{f['phase']}] {desc}")
        print(f"  更新于 {updated}")
    print()
    return 0


# ----- mode: 特性详情 -----
def mode_feature(live: list[dict], archived: list[dict], feature_name: str) -> int:
    matched_live = [f for f in live if f["feature"] == feature_name]
    matched_arch = [f for f in archived if f["feature"] == feature_name]
    if not matched_live and not matched_arch:
        print(f"未找到特性 '{feature_name}' 相关文件。")
        return 1

    print(f"## 特性: {feature_name}\n")
    print("| 阶段 | 文件 | 状态 | 创建 | 更新 |")
    print("|------|------|------|------|------|")
    for f in sorted(matched_live + matched_arch, key=lambda x: x["phase"]):
        st = (f["fm"].get("status") or "").strip()
        sym = STATUS_SYMBOL.get(st, st or "?")
        created = _fmt_ts(f["fm"].get("created_at"))
        updated = _fmt_ts(f["fm"].get("updated_at"))
        print(f"| {f['phase']} | {f['filename']} | {sym} | {created} | {updated} |")
    print()

    # 局部一致性检查
    feature_anomalies = [a for a in consistency_check(matched_live)
                         if a.get("feature") == feature_name or feature_name in a.get("path", "")]
    if feature_anomalies:
        print(f"⚠️ 异常 ({len(feature_anomalies)}):\n")
        for a in feature_anomalies:
            print(f"- `{a['path']}` — {a['message']}")
        print()
    else:
        print("✓ 状态一致性检查通过\n")

    # 给归档建议
    process_complete = all(
        (f["fm"].get("status") or "") == "completed"
        for f in matched_live if f["category"] == "process"
    )
    if matched_live and process_complete:
        print(f"建议归档 → `/rpiv-loop:archive {feature_name}`\n")

    return 0


# ----- mode: 一致性检查 -----
def mode_check(live: list[dict], errors: list[dict]) -> int:
    anomalies = consistency_check(live)
    if not anomalies and not errors:
        print("✓ 全部一致,无异常\n")
        return 0
    if errors:
        print(f"## ❓ frontmatter 解析失败 ({len(errors)})\n")
        for e in errors:
            print(f"- {e['path']} — {e['error']}")
        print()
    if anomalies:
        print(f"## ⚠️ 一致性异常 ({len(anomalies)})\n")
        for a in anomalies:
            kind = a["kind"]
            fixable = "可自动修复" if a.get("fixable") else "需用户决策"
            print(f"- `{a['path']}`")
            print(f"  [{kind}] {a['message']}")
            print(f"  → {fixable}")
        print(f"\n执行修复: `/rpiv-loop:flow-status fix`\n")
    return 0


# ----- mode: 自动修复 + LLM payload -----
def _apply_auto_fix(live: list[dict], anomaly: dict, now_iso: str) -> bool:
    """对单个 fixable=True 异常项做原地修复。返回是否成功修复。"""
    target = next((f for f in live if f["path"] == anomaly["path"]), None)
    if not target:
        return False
    action = anomaly.get("suggested_action")
    file_path = Path(target["abs_path"])
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return False

    if action in ("auto_update_prd_to_completed", "auto_update_plan_to_completed"):
        new_text = _replace_fm_field(text, "status", "completed")
        new_text = _replace_fm_field(new_text, "updated_at", now_iso)
    elif action == "auto_change_todo_superseded_to_archived":
        new_text = _replace_fm_field(text, "status", "archived")
        new_text = _replace_fm_field(new_text, "updated_at", now_iso)
    else:
        return False

    if new_text == text:
        return False
    file_path.write_text(new_text, encoding="utf-8")
    return True


def _replace_fm_field(text: str, key: str, new_value: str) -> str:
    """替换 frontmatter 内某 scalar 字段值。找不到则插入到第一行 frontmatter 之后。"""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return text
    block = m.group(1)
    pattern = re.compile(rf"^({re.escape(key)}):\s*.*?\s*$", re.MULTILINE)
    if pattern.search(block):
        new_block = pattern.sub(rf"\1: {new_value}", block, count=1)
    else:
        new_block = block + f"\n{key}: {new_value}"
    return text[:m.start(1)] + new_block + text[m.end(1):]


def mode_fix(live: list[dict], errors: list[dict], rpiv_dir: Path) -> int:
    anomalies = consistency_check(live)
    if not anomalies:
        print("✓ 无异常需修复\n")
        return 0

    auto_fixable = [a for a in anomalies if a.get("fixable")]

    now_iso = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    fixed: list[dict] = []
    failed: list[dict] = []

    print(f"## 自动修复 ({len(auto_fixable)} 项可修复)\n")
    for a in auto_fixable:
        ok = _apply_auto_fix(live, a, now_iso)
        if ok:
            fixed.append(a)
            print(f"✓ {a['path']} — {a['message']}")
        else:
            failed.append(a)
            print(f"✗ {a['path']} — 修复失败（建议手工处理）")
    if not auto_fixable:
        print("（无可自动修复项）")
    print()

    # 重新扫描 + 重算异常,过滤掉已被这一轮 auto-fix 顺带消除的连带异常
    live_after, _, _ = scan_rpiv(rpiv_dir)
    remaining = consistency_check(live_after)
    # 排除新一轮中仍标为 fixable 的(下次跑 fix 还能自动处理,不需要 LLM)
    manual = [a for a in remaining if not a.get("fixable")]

    if manual or failed:
        print(f"## ⚠️ 需用户决策 ({len(manual) + len(failed)} 项)\n")
        for a in manual + failed:
            print(f"- `{a['path']}` — {a['message']}")
        print()
        payload = {
            "action": "ask_user_for_decisions",
            "items": manual + failed,
            "auto_fixed": [a["path"] for a in fixed],
        }
        print("__NEED_LLM__")
        print(json.dumps(payload, ensure_ascii=False))
        print()
        print(PROTOCOL_INSTRUCTIONS)
    else:
        print(f"全部 {len(fixed)} 项已自动修复,无残留异常。\n")

    return 0


# ----- main -----
def main() -> int:
    parser = argparse.ArgumentParser(description="rpiv-loop:flow-status (Python)")
    parser.add_argument("mode", nargs="?", default="", help="模式: 留空=精简摘要 | all | pending | in-progress | completed | <feature> | check | fix")
    parser.add_argument("--rpiv-dir", default=None, help="rpiv 目录绝对路径,默认 ./rpiv")
    args = parser.parse_args()

    cwd = Path.cwd()
    rpiv_dir = Path(args.rpiv_dir) if args.rpiv_dir else cwd / "rpiv"
    if not rpiv_dir.is_dir():
        print(f"❌ rpiv/ 目录不存在: {rpiv_dir}", file=sys.stderr)
        return 2

    try:
        live, archived, errors = scan_rpiv(rpiv_dir)
    except Exception as exc:
        print(f"❌ 扫描失败: {exc}", file=sys.stderr)
        return 2

    mode = args.mode.strip()
    if mode == "":
        return mode_summary(live, archived, errors)
    if mode == "all":
        return mode_all(live, archived, errors)
    if mode in ("pending", "in-progress", "completed", "open", "superseded", "archived"):
        return mode_filter(live + archived, mode)
    if mode == "check":
        return mode_check(live, errors)
    if mode == "fix":
        return mode_fix(live, errors, rpiv_dir)
    # 否则当作 feature name
    return mode_feature(live, archived, mode)


if __name__ == "__main__":
    sys.exit(main())
