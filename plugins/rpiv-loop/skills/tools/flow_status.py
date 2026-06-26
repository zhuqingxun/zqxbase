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
    # 不含 handoff：classify_file 永不返回 handoff，handoff 文件按 process 分组/显示。
    # 其 status 合法性不走 category 体系，改用下面的 HANDOFF_LEGAL_STATUS 单独审计。
    # 「handoff 不作为 category」这一结构由 test_rpiv_legal_status_consistency.py 守卫，勿把 handoff 塞进本 dict。
}

# handoff 票据 status 审计兜底：与 hook validate_rpiv_status.py 的 handoff 枚举一致。
# 用途——hook 在写入时独占强制 handoff 合法性；但若有人绕过 hook（手工编辑 / 外部脚本）
# 写出非法 status 的 handoff，flow_status 的一致性审计用此常量兜底抓出。
# 与 hook + spec 的一致性由 test_rpiv_legal_status_consistency.py 守卫。
HANDOFF_LEGAL_STATUS = {"pending", "archived"}

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
# 重跑命令用本脚本运行时的真实绝对路径(Path(__file__))拼接,
# 禁止硬编码本机绝对路径——否则换安装目录/换 OS 即指向不存在路径。
_SELF_CHECK_CMD = f"uv run --no-project python {Path(__file__).resolve().as_posix()} check"
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
4. 全部处理完后,重跑下列命令确认无残留异常,输出最终 check 结果:
   `""" + _SELF_CHECK_CMD + """`
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


def is_handoff_name(filename: str) -> bool:
    """文件名是否为 handoff 票据：`handoff-` 前缀 或 `-handoff` 后缀。

    与 hooks/validate_rpiv_status.py 的 classify() 识别口径对齐，使所有发现/列举
    工具与校验层一致，避免后缀命名的 handoff 对工具隐形。
    """
    stem = filename[:-3] if filename.lower().endswith(".md") else filename
    low = stem.lower()
    return low.startswith("handoff-") or low.endswith("-handoff")


def legal_status_for(f: dict) -> set:
    """handoff 文件按 HANDOFF_LEGAL_STATUS 审计（兜底 hook 被绕过），其余按 category 枚举。

    handoff 不在 LEGAL_STATUS 的 category 体系内（classify_file 永不返回 handoff，见两常量注释
    与守卫测试），但其 status 仍需校验——用独立的 HANDOFF_LEGAL_STATUS，与 hook 强制层一致。
    """
    if is_handoff_name(f.get("filename", "")):
        return HANDOFF_LEGAL_STATUS
    return LEGAL_STATUS.get(f["category"], set())


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
            if any(name.startswith(prefix) for prefix, _ in AUX_PREFIXES) or is_handoff_name(name):
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


# ----- 多子项目聚合扫描 -----
def read_subprojects_config(primary_rpiv: Path, cwd: Path) -> list[Path]:
    """读取聚合清单 <primary_rpiv>/subprojects.txt。

    每行一个 rpiv 目录路径（绝对或相对 cwd），`#` 开头与空行忽略。
    用于伞目录场景：本目录 rpiv 无 md，但希望一条命令看到下属子项目的 rpiv。
    文件不存在返回 []。
    """
    cfg = primary_rpiv / "subprojects.txt"
    if not cfg.is_file():
        return []
    dirs: list[Path] = []
    try:
        lines = cfg.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        p = Path(s)
        if not p.is_absolute():
            p = (cwd / p).resolve()
        dirs.append(p)
    return dirs


def scan_many(rpiv_dirs: list[Path]) -> tuple[list[dict], list[dict], list[dict]]:
    """聚合扫描多个 rpiv 目录。

    给每条记录打 project 标签（= rpiv 目录的父目录名），并把 path 前缀成
    `<project>/...`，使跨子项目的路径唯一、可读。abs_path 不变（fix 仍能定位）。
    """
    live_all: list[dict] = []
    arch_all: list[dict] = []
    err_all: list[dict] = []
    for d in rpiv_dirs:
        proj = d.parent.name
        if not d.is_dir():
            err_all.append({"path": str(d), "error": "rpiv 目录不存在", "project": proj})
            continue
        live, arch, errs = scan_rpiv(d)
        for f in live:
            f["project"] = proj
            f["path"] = f"{proj}/{f['path']}"
        for f in arch:
            f["project"] = proj
            f["path"] = f"{proj}/{f['path']}"
        for e in errs:
            e["project"] = proj
            e["path"] = f"{proj}/{e['path']}"
        live_all += live
        arch_all += arch
        err_all += errs
    return live_all, arch_all, err_all


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

    # 按 (project, feature) 命名空间分组：聚合多子项目时 project 区分同名 feature，
    # 单项目时 project 为 ""（不影响行为）。
    by_feature: dict[tuple, dict[str, dict]] = {}
    for f in live:
        if f["category"] != "process" or f["phase"] == "Unknown":
            continue
        fkey = (f.get("project", ""), f["feature"])
        by_feature.setdefault(fkey, {})[f["phase"]] = f

    # 1. status 合法性
    for f in live:
        status = (f["fm"].get("status") or "").strip()
        legal = legal_status_for(f)
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
    for (_proj, feature), phases in by_feature.items():
        prd = phases.get("PRD")
        plan = phases.get("Plan")
        if plan and prd:
            plan_status = (plan["fm"].get("status") or "").strip()
            prd_status = (prd["fm"].get("status") or "").strip()
            if plan_status in ("completed", "in-progress") and prd_status in ("pending", "in-progress"):
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
    for (_proj, feature), phases in by_feature.items():
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
                elif (plan["fm"].get("status") or "").strip() in ("pending", "in-progress"):
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
            # 带时区时间戳归一到 naive 再比较（48h 阈值下小时级偏移可忽略）；
            # 否则 tz-aware 时间戳会因与 naive now 不可比而被静默漏检。
            if updated is not None and updated.tzinfo is not None:
                updated = updated.replace(tzinfo=None)
            if updated and now - updated > cutoff:
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
    aux_brainstorms = {(f.get("project", ""), f["feature"]): f for f in live if f["phase"] == "Brainstorm"}
    for (_proj, feature), bs in aux_brainstorms.items():
        if (bs["fm"].get("status") or "") in ("pending", "in-progress"):
            phases = by_feature.get((_proj, feature), {})
            if "PRD" not in phases:
                anomalies.append({
                    "path": bs["path"],
                    "kind": "brainstorm_no_prd",
                    "message": "brainstorm-summary 存在但未推进到 PRD",
                    "fixable": False,
                    "suggested_action": "remind_user",
                })

    # 9. exec-report 存在但 Plan 不是 completed
    for (_proj, feature), phases in by_feature.items():
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


def _fmt_date(s: str | None) -> str:
    """创建日期格式：YYYY-MM-DD（含年份，避免跨年混淆，不显示时分）。"""
    if not s:
        return "—"
    ts = _parse_ts(s)
    if ts:
        return ts.strftime("%Y-%m-%d")
    return s[:10]


def _short_desc(fm: dict) -> str:
    return fm.get("title") or fm.get("description") or ""


# ----- mode: 精简摘要 -----
def mode_summary(live: list[dict], archived: list[dict], errors: list[dict],
                 aggregated: bool = False) -> int:
    anomalies = consistency_check(live)

    def _pp(f: dict) -> str:
        """聚合模式下给明细行加 [project] 前缀；单项目模式返回空串（输出保持原样）。"""
        return f"[{f.get('project')}] " if aggregated and f.get("project") else ""

    process_files = [f for f in live if f["category"] == "process"]
    todo_files = [f for f in live if f["category"] == "todo"]
    aux_files = [f for f in live if f["category"] == "aux"]

    # archived 状态的 todo 不是活跃待办（理应已归位 rpiv/archive/）。
    # 活跃表与计数仅含非 archived；滞留 todo/ 的 archived 单列告警，避免 silent 丢失。
    active_todos = [f for f in todo_files if (f["fm"].get("status") or "") != "archived"]
    misplaced_archived_todos = [f for f in todo_files if (f["fm"].get("status") or "") == "archived"]

    n_in_progress = sum(1 for f in process_files if (f["fm"].get("status") or "") == "in-progress")
    n_pending = sum(1 for f in process_files if (f["fm"].get("status") or "") == "pending")
    n_completed = sum(1 for f in process_files if (f["fm"].get("status") or "") == "completed")

    todo_open = sum(1 for f in active_todos if (f["fm"].get("status") or "") == "open")
    todo_in_prog = sum(1 for f in active_todos if (f["fm"].get("status") or "") == "in-progress")
    todo_done = sum(1 for f in active_todos if (f["fm"].get("status") or "") == "completed")

    print("## 流程状态（聚合）\n" if aggregated else "## 流程状态\n")
    parts = [f"⚠️ 异常 {len(anomalies)}" if anomalies else "",
             f"🔄 进行中 {n_in_progress}",
             f"⏳ 待处理 {n_pending}",
             f"✓ 已完成 {n_completed}",
             f"📦 已归档 {len(archived)}",
             f"📋 Todo {len(active_todos)}"]
    print(" | ".join(p for p in parts if p))
    print()

    if aggregated:
        # 按子项目分组的计数表（仅展示有内容的子项目）
        proj_stats: dict[str, dict[str, int]] = {}

        def _slot(name: str) -> dict[str, int]:
            return proj_stats.setdefault(name, {"in": 0, "pend": 0, "comp": 0, "todo": 0, "arch": 0})

        for f in process_files:
            st = (f["fm"].get("status") or "")
            slot = _slot(f.get("project", "?"))
            if st == "in-progress":
                slot["in"] += 1
            elif st == "pending":
                slot["pend"] += 1
            elif st == "completed":
                slot["comp"] += 1
        for f in active_todos:
            _slot(f.get("project", "?"))["todo"] += 1
        for f in archived:
            _slot(f.get("project", "?"))["arch"] += 1
        if proj_stats:
            print("### 📦 按子项目\n")
            print("| 子项目 | 🔄 | ⏳ | ✓ | 📋 Todo | 📦 |")
            print("|--------|----|----|----|---------|----|")
            for name in sorted(proj_stats):
                d = proj_stats[name]
                print(f"| {name} | {d['in']} | {d['pend']} | {d['comp']} | {d['todo']} | {d['arch']} |")
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
            print(f"- {_pp(f)}{f['filename']} — {desc} [{f['phase']}]")
        print()

    pending = [f for f in process_files if (f["fm"].get("status") or "") == "pending"]
    if pending:
        print("### ⏳ 待处理\n")
        for f in pending:
            desc = _short_desc(f["fm"])
            print(f"- {_pp(f)}{f['filename']} — {desc} [{f['phase']}]")
        print()

    # 已完成：按 (project, feature) 聚合（单项目时 project 为 ""，显示同原样）
    completed_by_feature: dict[tuple, dict[str, dict]] = {}
    for f in process_files:
        if (f["fm"].get("status") or "") == "completed":
            fkey = (f.get("project", "") if aggregated else "", f["feature"])
            completed_by_feature.setdefault(fkey, {})[f["phase"]] = f
    if completed_by_feature:
        print("### ✓ 已完成（建议归档 → `/rpiv-loop:archive all`）\n")
        for (proj, feature), phases in sorted(completed_by_feature.items()):
            tags = " ".join(f"{p} ✓" for p in SUMMARY_PHASES if p in phases)
            extras = [p for p in phases if p not in SUMMARY_PHASES]
            if extras:
                tags += " " + " ".join(f"{p} ✓" for p in extras)
            label = f"[{proj}] {feature}" if proj else feature
            print(f"- {label} — {tags}")
        print()

    if active_todos:
        print(f"### 📋 Todo (open: {todo_open} | in-progress: {todo_in_prog} | completed: {todo_done})\n")
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        priority_icon = {"high": "🔴 high", "medium": "🟡 medium", "low": "🔵 low"}
        type_icon = {"feature": "✨", "todo": "📝", "issue": "🐛", "fix": "🔧"}
        status_icon = {"open": "🔓 open", "in-progress": "🔄 in-progress",
                       "completed": "✓ completed", "archived": "📦 archived"}

        def _todo_sort_key(f: dict) -> tuple:
            pri = (f["fm"].get("priority") or "").lower()
            typ = f["fm"].get("type") or ""
            proj = f.get("project", "") if aggregated else ""
            return (proj, priority_rank.get(pri, 99), typ, f["feature"])

        if aggregated:
            print("| 子项目 | 优先级 | 类型 | 状态 | 创建 | 标识 | 标题 |")
            print("|--------|--------|------|------|------|------|------|")
        else:
            print("| 优先级 | 类型 | 状态 | 创建 | 标识 | 标题 |")
            print("|--------|------|------|------|------|------|")
        for f in sorted(active_todos, key=_todo_sort_key):
            pri = (f["fm"].get("priority") or "").lower()
            pri_disp = priority_icon.get(pri, "—")
            typ = f["fm"].get("type") or ""
            typ_disp = f"{type_icon.get(typ, '📌')} {typ}" if typ else "—"
            status = f["fm"].get("status") or "?"
            st_disp = status_icon.get(status, status)
            created = _fmt_date(f["fm"].get("created_at"))
            title = _short_desc(f["fm"]).replace("|", r"\|")
            if aggregated:
                print(f"| {f.get('project', '?')} | {pri_disp} | {typ_disp} | {st_disp} | {created} | {f['feature']} | {title} |")
            else:
                print(f"| {pri_disp} | {typ_disp} | {st_disp} | {created} | {f['feature']} | {title} |")
        print()

    if misplaced_archived_todos:
        print(f"> ⚠️ {len(misplaced_archived_todos)} 个 archived 状态的 todo 仍滞留 `rpiv/todo/`，应移至 `rpiv/archive/`：")
        for f in sorted(misplaced_archived_todos, key=lambda x: x["path"]):
            print(f">   - `{f['path']}`")
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
def mode_all(live: list[dict], archived: list[dict], errors: list[dict],
             aggregated: bool = False) -> int:
    process_files = [f for f in live if f["category"] == "process"]
    by_feature: dict[tuple, dict[str, dict]] = {}
    for f in process_files:
        fkey = (f.get("project", "") if aggregated else "", f["feature"])
        by_feature.setdefault(fkey, {})[f["phase"]] = f

    print("## 全部特性状态（聚合）\n" if aggregated else "## 全部特性状态\n")
    first_col = "子项目/特性" if aggregated else "特性"
    header = f"| {first_col} | " + " | ".join(ALL_TABLE_PHASES) + " | 状态 |"
    sep = "|------|" + "|".join(["-----"] * len(ALL_TABLE_PHASES)) + "|------|"
    print(header)
    print(sep)
    for (proj, feature) in sorted(by_feature.keys()):
        phases = by_feature[(proj, feature)]
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
        label = f"[{proj}] {feature}" if proj else feature
        print(f"| {label} | " + " | ".join(cells) + f" | {overall} |")
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
def _run_single(mode: str, rpiv_dir: Path) -> int:
    """单 rpiv 目录：保持原行为，输出与改造前一致。"""
    if not rpiv_dir.is_dir():
        print(f"❌ rpiv/ 目录不存在: {rpiv_dir}", file=sys.stderr)
        return 2
    try:
        live, archived, errors = scan_rpiv(rpiv_dir)
    except Exception as exc:
        print(f"❌ 扫描失败: {exc}", file=sys.stderr)
        return 2

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
    return mode_feature(live, archived, mode)


def _run_aggregated(mode: str, rpiv_dirs: list[Path]) -> int:
    """多 rpiv 目录聚合：用于伞目录一条命令看全部子项目。"""
    try:
        live, archived, errors = scan_many(rpiv_dirs)
    except Exception as exc:
        print(f"❌ 聚合扫描失败: {exc}", file=sys.stderr)
        return 2

    if mode == "":
        return mode_summary(live, archived, errors, aggregated=True)
    if mode == "all":
        return mode_all(live, archived, errors, aggregated=True)
    if mode in ("pending", "in-progress", "completed", "open", "superseded", "archived"):
        return mode_filter(live + archived, mode)
    if mode == "check":
        return mode_check(live, errors)
    if mode == "fix":
        # 聚合模式不安全做 fix：archive 提示依赖子项目 cwd，原地改文件易出错。
        anomalies = consistency_check(live)
        print("## ⚠️ 聚合模式不支持 fix\n")
        if anomalies:
            projs = sorted({a.get("project") or a["path"].split("/", 1)[0] for a in anomalies})
            print(f"检测到 {len(anomalies)} 项异常，分布在子项目: {', '.join(projs)}\n")
            print("请 `cd` 到对应子项目后单独跑 `/rpiv-loop:flow-status fix`。\n")
        else:
            print("（聚合范围内无异常需修复）\n")
        return 0
    return mode_feature(live, archived, mode)


def main() -> int:
    parser = argparse.ArgumentParser(description="rpiv-loop:flow-status (Python)")
    parser.add_argument("mode", nargs="?", default="", help="模式: 留空=精简摘要 | all | pending | in-progress | completed | <feature> | check | fix")
    parser.add_argument("--rpiv-dir", action="append", default=None,
                        help="rpiv 目录绝对路径；可重复指定多个做聚合。默认 ./rpiv；"
                             "若 ./rpiv/subprojects.txt 存在则自动聚合其中列出的子项目 rpiv。")
    args = parser.parse_args()

    cwd = Path.cwd()
    mode = args.mode.strip()

    # 解析要扫描的 rpiv 目录集合 + 是否聚合
    if args.rpiv_dir:
        rpiv_dirs = [Path(d) for d in args.rpiv_dir]
        aggregated = len(rpiv_dirs) > 1
    else:
        primary = cwd / "rpiv"
        extra = read_subprojects_config(primary, cwd) if primary.is_dir() else []
        if extra:
            # 伞目录场景：本目录 rpiv（通常无 md）+ 配置列出的子项目一起聚合
            rpiv_dirs = ([primary] if primary.is_dir() else []) + extra
            aggregated = True
        else:
            rpiv_dirs = [primary]
            aggregated = False

    if aggregated:
        return _run_aggregated(mode, rpiv_dirs)
    return _run_single(mode, rpiv_dirs[0])


if __name__ == "__main__":
    sys.exit(main())
