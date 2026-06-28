# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""meta_io.py — mint 插件共享元数据 IO 模块

集中实现：
- meta.yaml / workspace.yaml 的读写（保序）
- 规则推理（compute_next_hints）
- blocker 生命周期（add / resolve）
- last_action 双源 max 计算
- find_workspace_root / scan_meetings
- init_workspace

CLI 子命令（供 SKILL.md Bash 调用）：
    refresh-last-action <meeting_dir>
    compute-next-hints <meeting_dir> [--workspace <root>]
    find-workspace-root [cwd]
    scan-meetings <workspace_root>
    init-workspace <root> <scenario> <goal> <deliverable1,deliverable2,...>
    validate-meta <meeting_dir>
    load-workspace <root>
    add-blocker <meeting_dir> <type> <description> [suggested_action]
    resolve-blockers <meeting_dir> <substring>
    set-stage <meeting_dir> <stage> --status <s> [--version N] [--completed-at ISO] [--param k=v]... [--field k=v]...
    set-cursor <meeting_dir> <cursor> [--desc <text>]
    add-revision <meeting_dir> --desc <text> [--files <p1,p2>] [--type patch|revise|sync] [--timestamp ISO] [--last-action-desc <text>]
    types-add <root> <id> <name> [--default-template-id <id>]
    types-list <root>
    types-remove <root> <id>
    templates-add <root> <id> <name> <file> <applies_to> [--set-default]
    templates-list <root>
    templates-remove <root> <id>
    resolve-template <meeting_dir> [--template-override <id|path>]
    summarize-collect <workspace_root>
    summarize-backup-outputs <workspace_root>
    summarize-read-state <workspace_root>
    summarize-write-state <workspace_root>  # stdin: state JSON
    summarize-detect-delta <workspace_root>
    summarize-find-anchors <file_abs>
    summarize-sha256 <file_abs>
    summarize-splice-text <file_abs> --at-line <N> --mode {before|after}  # stdin: content

JSON 输出均使用 ensure_ascii=False 保留中文。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

META_FIELD_ORDER = [
    "project",
    "created",
    "source_audio",
    "stages",
    "revisions",
    "desensitization",
    "intent",
    "interviewee_type",
    "current",
    "next_hints",
]

WORKSPACE_FIELD_ORDER = ["workspace", "intent", "interviewee_types", "templates"]

TYPE_FIELD_ORDER = ["id", "name", "default_template_id"]
TEMPLATE_FIELD_ORDER = ["id", "name", "file", "applies_to"]

PRESET_TYPE_ID_MAP = {
    "内部员工": "internal",
    "外部员工 / 服务对象": "external",
    "领导层": "leader",
}

ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

REQUIRED_META_FIELDS = ["intent", "current", "next_hints"]

STAGE_ORDER = ["transcribe", "refine", "polish", "extract"]

STATUS_ENUM = ["pending", "in_progress", "completed", "failed"]

# --- deliverables 预设 single-source ---------------------------------------
# 历史上同一组业务常量分散在三处（本常量 / init SKILL Q2 / scenario-presets.md），
# 仅靠「约定一致」维持。现以本文件为机器单一源，并由
# `deliverable-presets` CLI 对外暴露；三处一致性由
# tests/mint-types/test_deliverable_presets.py 的守卫不变式机器保证：
#   set(_filter_deliverables(s, DELIVERABLE_SELECTABLE)) == set(DELIVERABLE_PRESETS[s])
#
# DELIVERABLE_SELECTABLE: init Q2 向用户展示的并集选项（AskUserQuestion 上限 4 项）。
# DELIVERABLE_PRESETS:    各 scenario 经 _filter_deliverables 过滤补齐后的稳定默认集快照。
DELIVERABLE_SELECTABLE = ["观点分析", "行动项", "决议清单", "要点摘要"]

DELIVERABLE_PRESETS: dict[str, list[str]] = {
    "interview": ["观点分析", "行动项", "精华语录", "要点摘要"],
    "meeting": ["决议清单", "行动项", "问题清单", "要点摘要"],
}

# 向后兼容别名（simulate_init.py 等既有消费方按名引用）
INTERVIEW_DELIVERABLES = DELIVERABLE_PRESETS["interview"]
MEETING_DELIVERABLES = DELIVERABLE_PRESETS["meeting"]

STATE_SCHEMA_VERSION = 2  # v3.0: dynamic outputs list + split_mode + template_used (旧 v2 schema=1)
STALE_VERSION = 1  # mint:stale HTML 注释 schema, 与 state schema 解耦, 不随 STATE_SCHEMA_VERSION 升级

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

STALE_RE = re.compile(
    r"<!--\s*mint:stale\s+"
    r"v=(?P<v>\d+)\s+"
    r"ts=(?P<ts>[\dT:\-+]+)\s+"
    r"new_meetings=(?P<new>\S*)\s+"
    r"changed_meetings=(?P<changed>\S*)\s+"
    r"removed_meetings=(?P<removed>\S*)\s*"
    r"-->"
)


# ============================================================
# meta.yaml IO
# ============================================================


def _reorder_dict(data: dict, order: list[str]) -> dict:
    """按指定顺序重排字典，未列出的 key 追加到末尾"""
    out = {}
    for k in order:
        if k in data:
            out[k] = data[k]
    for k in data:
        if k not in out:
            out[k] = data[k]
    return out


def load_meta(path: Path) -> dict:
    """读取 meta.yaml 并校验必填字段

    缺 intent / current / next_hints 中任何一项抛 KeyError，消息含字段名。
    """
    if not path.exists():
        raise FileNotFoundError(f"meta.yaml 不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for field in REQUIRED_META_FIELDS:
        if field not in data:
            raise KeyError(f"meta.yaml 缺少必要字段 {field}: {path}")
    return data


def save_meta(path: Path, meta: dict) -> None:
    """写入 meta.yaml，保持字段顺序，allow_unicode"""
    ordered = _reorder_dict(meta, META_FIELD_ORDER)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            ordered,
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )


def validate_meta(path: Path) -> None:
    """仅做必填字段校验，用于 CLI validate-meta 子命令"""
    load_meta(path)


# ============================================================
# workspace.yaml IO
# ============================================================


def load_workspace(path: Path) -> dict:
    """读取 .mint/workspace.yaml"""
    if not path.exists():
        raise FileNotFoundError(f"workspace.yaml 不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_workspace(path: Path, ws: dict) -> None:
    """写入 workspace.yaml，保持字段顺序"""
    ordered = _reorder_dict(ws, WORKSPACE_FIELD_ORDER)
    if "workspace" in ordered and isinstance(ordered["workspace"], dict):
        ordered["workspace"] = _reorder_dict(
            ordered["workspace"], ["name", "created_at", "scenario"]
        )
    if "intent" in ordered and isinstance(ordered["intent"], dict):
        ordered["intent"] = _reorder_dict(ordered["intent"], ["goal", "deliverables"])
    if "interviewee_types" in ordered and isinstance(
        ordered["interviewee_types"], list
    ):
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


# ============================================================
# types / templates helpers
# ============================================================


def normalize_id(name: str, existing_ids: set[str], prefix: str = "") -> str:
    """将 name 规范化为 kebab-case id，冲突自动追加 -2/-3

    优先命中 PRESET_TYPE_ID_MAP；纯 ASCII 走小写 + 非字母数字换 -；含非 ASCII 报错。
    """
    if name in PRESET_TYPE_ID_MAP:
        candidate = PRESET_TYPE_ID_MAP[name]
        if prefix and not candidate.startswith(prefix):
            candidate = f"{prefix}{candidate}"
    elif all(ord(c) < 128 for c in name):
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if not base:
            raise ValueError(f"name 无法生成合法 id: {name}")
        if prefix and not base.startswith(prefix):
            base = f"{prefix}{base}"
        candidate = base
    else:
        raise ValueError(
            f"name 含非 ASCII 字符，请改用英文名或手工指定 id: {name}"
        )

    result = candidate
    i = 2
    while result in existing_ids:
        result = f"{candidate}-{i}"
        i += 1
    return result


def scan_meeting_type_usage(root: Path) -> dict[str, list[str]]:
    """扫描工作区所有会议 meta.yaml 的 interviewee_type 字段

    返回 {type_id: [meeting_dir, ...]}。扫描失败的会议静默跳过。
    """
    usage: dict[str, list[str]] = {}
    for m in scan_meetings(root):
        meta_path = root / m["dir"] / "meta.yaml"
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
            tid = meta.get("interviewee_type")
            if tid:
                usage.setdefault(tid, []).append(m["dir"])
        except Exception:
            continue
    return usage


def scan_meeting_template_overrides(root: Path) -> dict[str, list[str]]:
    """扫描工作区所有会议 meta.stages.polish.params.template_override 字段

    返回 {template_id: [meeting_dir, ...]}。
    """
    overrides: dict[str, list[str]] = {}
    for m in scan_meetings(root):
        meta_path = root / m["dir"] / "meta.yaml"
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
            stages = meta.get("stages") or {}
            polish = stages.get("polish") or {}
            params = polish.get("params") or {}
            tpl_id = params.get("template_override")
            if tpl_id:
                overrides.setdefault(tpl_id, []).append(m["dir"])
        except Exception:
            continue
    return overrides


# ============================================================
# summarize helpers（mint:summarize 专用）
# ============================================================


def load_desensitization_registry(root: Path) -> dict:
    """读取 .mint/desensitization_registry.yaml

    优先从 .mint/ 下读取（新位置，由 upgrade_workspace 迁入）；
    不存在时兼容工作区根下的老位置。读取失败（文件不存在或 YAML 异常）返回空 dict。

    返回原 YAML 结构（含 next_id、registry 子字典）。
    """
    candidates = [
        root / ".mint" / "desensitization_registry.yaml",
        root / "desensitization_registry.yaml",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            with p.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("脱敏 registry 读取失败 %s: %s", p, e)
            return {}
    return {}


def resolve_polish_source(
    meeting_dir_abs: Path, registry: dict, meeting_dir_name: str
) -> tuple[Path | None, bool]:
    """为单会议选择 polish 源文件

    优先级：
      1. 04_编辑稿/受访者_{NN}_结构化分析_脱敏稿.md（NN 来自 registry；按 project == dir_name 查询）
      2. 04_编辑稿/{project_name}_结构化分析.md（原版，从 meta.yaml.project 取）
      3. 均不存在 → (None, False)

    返回 (path_or_None, is_desensitized)。
    """
    edit_dir = meeting_dir_abs / "04_编辑稿"
    if not edit_dir.is_dir():
        return None, False

    reg_entries = registry.get("registry") or {}
    desen_code: str | None = None
    for code, entry in reg_entries.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("project") == meeting_dir_name:
            desen_code = code
            break

    if desen_code:
        desen_path = edit_dir / f"{desen_code}_结构化分析_脱敏稿.md"
        if desen_path.is_file():
            return desen_path, True

    meta_path = meeting_dir_abs / "meta.yaml"
    project_name: str | None = None
    if meta_path.is_file():
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                m = yaml.safe_load(f) or {}
            project_name = m.get("project")
        except Exception:
            project_name = None

    candidates: list[Path] = []
    if project_name:
        candidates.append(edit_dir / f"{project_name}_结构化分析.md")
    candidates.append(edit_dir / f"{meeting_dir_name}_结构化分析.md")
    for c in candidates:
        if c.is_file():
            return c, False

    return None, False


def collect_summarize_data(root: Path) -> dict:
    """为 mint:summarize 聚合一次 CLI 即需的所有决策数据

    前置校验：
      - workspace.yaml 存在且 scenario == interview
      - templates[] 非空
    扫会议：
      - polish.status == completed 且 interviewee_type 非空 → 合格候选
      - 其他 → 记入 skipped_meetings（含原因）
      - 合格会议再用 resolve_polish_source 选源文件；选不到则降级记 skipped
    失败时抛 ValueError（main() 统一转 exit 2 + "ERROR: ..."）。
    """
    ws_path = root / ".mint" / "workspace.yaml"
    ws = load_workspace(ws_path)
    scenario = (ws.get("workspace") or {}).get("scenario")
    if scenario != "interview":
        raise ValueError("summarize 仅 interview 场景可用")

    templates_raw = ws.get("templates") or []
    templates: list[dict] = []
    for t in templates_raw:
        if not isinstance(t, dict):
            continue
        file_rel = t.get("file") or ""
        file_abs = (root / file_rel).resolve() if file_rel else None
        templates.append(
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "file": file_rel,
                "file_abs": (
                    str(file_abs).replace("\\", "/") if file_abs else None
                ),
                "applies_to": list(t.get("applies_to") or []),
            }
        )
    if not templates:
        raise ValueError("workspace.yaml 无 templates；请先跑 /mint:templates add 注册访谈提纲")

    types_raw = ws.get("interviewee_types") or []
    types: list[dict] = [
        {
            "id": t.get("id"),
            "name": t.get("name"),
            "default_template_id": t.get("default_template_id"),
        }
        for t in types_raw
        if isinstance(t, dict)
    ]

    registry = load_desensitization_registry(root)

    eligible: list[dict] = []
    skipped: list[dict] = []

    for m in scan_meetings(root):
        dir_name = m["dir"]
        meta_path = root / dir_name / "meta.yaml"
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        except Exception as e:
            skipped.append(
                {"dir": dir_name, "reason": f"meta.yaml 读取失败: {e}"}
            )
            continue

        polish_status = (
            ((meta.get("stages") or {}).get("polish") or {}).get("status")
        )
        if polish_status != "completed":
            skipped.append(
                {"dir": dir_name, "reason": "polish.status != completed"}
            )
            continue

        interviewee_type = meta.get("interviewee_type")
        if not interviewee_type:
            skipped.append(
                {"dir": dir_name, "reason": "interviewee_type 未填"}
            )
            continue

        meeting_abs = root / dir_name
        src, is_desen = resolve_polish_source(meeting_abs, registry, dir_name)
        if src is None:
            skipped.append(
                {"dir": dir_name, "reason": "polish 源文件不存在（脱敏稿与原版均未找到）"}
            )
            continue

        stat = src.stat()
        eligible.append(
            {
                "dir": dir_name,
                "project": meta.get("project", dir_name),
                "interviewee_type": interviewee_type,
                "polish_source": str(src.relative_to(root)).replace("\\", "/"),
                "polish_source_abs": str(src.resolve()).replace("\\", "/"),
                "is_desensitized": is_desen,
                "polish_sha256": sha256_file(src),
                "polish_size_bytes": stat.st_size,
                "polish_mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )

    if not eligible:
        raise ValueError("无合格 polish 产物，请先跑 /mint:polish")

    return {
        "scenario": scenario,
        "workspace": {
            "name": (ws.get("workspace") or {}).get("name") or root.name,
            "root": str(root.resolve()).replace("\\", "/"),
        },
        "templates": templates,
        "types": types,
        "eligible_meetings": eligible,
        "skipped_meetings": skipped,
    }


def backup_summarize_outputs(root: Path, timestamp: str | None = None) -> dict:
    """备份 汇总分析/mint_*.md 到 汇总分析/old/{timestamp}/

    仅迁移 `mint_` 前缀 + `.md` 后缀文件；用户手工产物（如 `访谈观点汇总.docx/md/pdf`）不动。
    无旧产物时返回 {"backed_up_files": [], "backup_dir": None} 且不创建目录。
    备份目录已存在则抛 FileExistsError（ISO 秒级冲突极罕见）。

    timestamp 默认用 now()；Windows 文件名禁冒号，用 `%Y-%m-%dT%H-%M-%S`。
    """
    summary_dir = root / "汇总分析"
    summary_dir.mkdir(parents=True, exist_ok=True)

    targets = sorted(
        [p for p in summary_dir.glob("mint_*.md") if p.is_file()]
    )
    if not targets:
        return {"backed_up_files": [], "backup_dir": None}

    ts = timestamp or datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    backup_dir = summary_dir / "old" / ts
    if backup_dir.exists():
        raise FileExistsError(f"备份目录已存在: {backup_dir}")
    backup_dir.mkdir(parents=True, exist_ok=False)

    moved: list[str] = []
    for p in targets:
        dest = backup_dir / p.name
        shutil.move(str(p), str(dest))
        moved.append(p.name)

    return {
        "backed_up_files": moved,
        "backup_dir": str(backup_dir.relative_to(root)).replace("\\", "/"),
    }


# ============================================================
# summarize incremental helpers
# ============================================================


def _state_path(root: Path) -> Path:
    """返回 <root>/汇总分析/.summarize-state.json 路径"""
    return root / "汇总分析" / ".summarize-state.json"


def sha256_file(path: Path) -> str:
    """计算文件 SHA-256 (64KB chunk 流式读取)"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_summarize_state(root: Path) -> dict | None:
    """读取 .summarize-state.json；不存在返回 None；损坏抛 ValueError"""
    p = _state_path(root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f".summarize-state.json 损坏: {e}")


def write_summarize_state(root: Path, state: dict) -> dict:
    """写入 state 到 .summarize-state.json；自动打 schema_version 戳"""
    p = _state_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    state["schema_version"] = STATE_SCHEMA_VERSION
    p.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"written": True, "path": str(p.resolve()).replace("\\", "/")}


def parse_stale(text: str) -> dict | None:
    """解析首个 mint:stale 注释；无匹配返回 None"""
    m = STALE_RE.search(text)
    if not m:
        return None

    def split_csv(s: str) -> list[str]:
        return [x for x in s.split(",") if x]

    return {
        "v": int(m.group("v")),
        "ts": m.group("ts"),
        "new": split_csv(m.group("new")),
        "changed": split_csv(m.group("changed")),
        "removed": split_csv(m.group("removed")),
    }


def merge_stale(old: dict | None, delta: dict, ts: str) -> dict:
    """合并 stale: 老 state + 本次 delta (集合并).

    delta keys: new, changed, removed (均为 list[str]).
    优先级: removed > changed > new.
    """
    if old is None:
        return {
            "v": STALE_VERSION,
            "ts": ts,
            "new": sorted(set(delta.get("new", []))),
            "changed": sorted(set(delta.get("changed", []))),
            "removed": sorted(set(delta.get("removed", []))),
        }
    new_set = set(old.get("new", [])) | set(delta.get("new", []))
    changed_set = set(old.get("changed", [])) | set(delta.get("changed", []))
    removed_set = set(old.get("removed", [])) | set(delta.get("removed", []))
    # removed 优先 -> 从 new/changed 剔除
    new_set -= removed_set
    changed_set -= removed_set
    # changed 次优先 -> 从 new 剔除
    new_set -= changed_set
    return {
        "v": STALE_VERSION,
        "ts": ts,
        "new": sorted(new_set),
        "changed": sorted(changed_set),
        "removed": sorted(removed_set),
    }


def format_stale(state: dict) -> str:
    """序列化 stale 状态为单行 HTML 注释"""
    return (
        f"<!-- mint:stale v={state['v']} ts={state['ts']} "
        f"new_meetings={','.join(state['new'])} "
        f"changed_meetings={','.join(state['changed'])} "
        f"removed_meetings={','.join(state['removed'])} -->"
    )


def detect_summarize_delta(
    root: Path, current_split_mode: bool | None = None
) -> dict:
    """对比当前 collect 结果与 .summarize-state.json,返回 delta 结构.

    输出 keys:
        first_run: bool
        added / changed / removed: list[str] (meeting_dir)
        workspace_reorder: bool
        split_mode_changed: bool (v3.0+, 仅 current_split_mode 提供时有意义)
        new_types / new_templates: list[str] (id)
        current_meetings: dict[dir -> meeting snapshot]
        current_types_order / current_templates_order: list[str]

    Args:
        current_split_mode: 调用方传入的本次决策 split_mode (workspace.yaml + CLI flag).
            None 表示调用方未决策, 不做 split_mode_changed 检测.
    """
    data = collect_summarize_data(root)
    ws = load_workspace(root / ".mint" / "workspace.yaml")
    cur_types_order = [
        t.get("id") for t in (ws.get("interviewee_types") or [])
        if isinstance(t, dict) and t.get("id")
    ]
    cur_tpls_order = [
        t.get("id") for t in (ws.get("templates") or [])
        if isinstance(t, dict) and t.get("id")
    ]

    cur_meetings: dict[str, dict] = {}
    for m in data["eligible_meetings"]:
        cur_meetings[m["dir"]] = {
            "polish_source_abs": m["polish_source_abs"],
            "polish_sha256": m["polish_sha256"],
            "polish_size_bytes": m["polish_size_bytes"],
            "polish_mtime": m["polish_mtime"],
            "interviewee_type": m["interviewee_type"],
            "is_desensitized": m["is_desensitized"],
        }

    old = read_summarize_state(root)
    # v3.0: 旧 schema (state_version < 2) 的 state 视为 first_run, 强制全量
    # 因为 outputs 字段从 dict 改为 list, append 锚点逻辑也变, 增量不能跨 schema 续接
    if old is None or old.get("schema_version", 1) < STATE_SCHEMA_VERSION:
        return {
            "first_run": True,
            "added": sorted(cur_meetings.keys()),
            "changed": [],
            "removed": [],
            "workspace_reorder": False,
            "split_mode_changed": False,
            "new_types": cur_types_order,
            "new_templates": cur_tpls_order,
            "current_meetings": cur_meetings,
            "current_types_order": cur_types_order,
            "current_templates_order": cur_tpls_order,
        }

    old_meetings = old.get("meetings", {}) or {}
    added = sorted(d for d in cur_meetings if d not in old_meetings)
    removed = sorted(d for d in old_meetings if d not in cur_meetings)
    changed = sorted(
        d for d in cur_meetings
        if d in old_meetings
        and cur_meetings[d]["polish_sha256"] != old_meetings[d].get("polish_sha256")
    )

    old_ws = old.get("workspace_snapshot") or {}
    old_types_order = old_ws.get("types_order") or []
    old_tpls_order = old_ws.get("templates_order") or []

    def _order_changed(old_list: list[str], new_list: list[str]) -> bool:
        """交集顺序对比.纯新增不触发 reorder;删除/顺序调换触发 reorder."""
        common_old = [x for x in old_list if x in new_list]
        common_new = [x for x in new_list if x in old_list]
        return common_old != common_new

    reorder = (
        _order_changed(old_types_order, cur_types_order)
        or _order_changed(old_tpls_order, cur_tpls_order)
    )
    new_types = [t for t in cur_types_order if t not in old_types_order]
    new_tpls = [t for t in cur_tpls_order if t not in old_tpls_order]

    # v3.0: split_mode_changed 检测
    old_split_mode = old.get("split_mode")
    split_mode_changed = (
        current_split_mode is not None
        and old_split_mode is not None
        and old_split_mode != current_split_mode
    )

    return {
        "first_run": False,
        "added": added,
        "changed": changed,
        "removed": removed,
        "workspace_reorder": reorder,
        "split_mode_changed": split_mode_changed,
        "new_types": new_types,
        "new_templates": new_tpls,
        "current_meetings": cur_meetings,
        "current_types_order": cur_types_order,
        "current_templates_order": cur_tpls_order,
    }


def find_markdown_anchors(file_path: Path) -> dict:
    """解析 Markdown 报告 heading 结构.

    返回 {
        file: "abs path (POSIX)",
        total_lines: int,
        headings: [{
            level: int(1-6),
            text: str,
            line_start: int(1-based),
            line_end: int(1-based),
            content_end: int(1-based),
            parent_line: int(可选)
        }, ...]
    }
    代码围栏 ``` 内的 `#` 开头行不算 heading.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"报告文件不存在: {file_path}")
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    headings: list[dict] = []
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            headings.append({
                "level": len(m.group(1)),
                "text": m.group(2).strip(),
                "line_start": i,
            })

    total = len(lines)
    for idx, h in enumerate(headings):
        line_end = total
        for j in range(idx + 1, len(headings)):
            if headings[j]["level"] <= h["level"]:
                line_end = headings[j]["line_start"] - 1
                break
        h["line_end"] = line_end
        content_end = h["line_start"]
        for k in range(line_end, h["line_start"], -1):
            if lines[k - 1].strip():
                content_end = k
                break
        h["content_end"] = content_end
        for j in range(idx - 1, -1, -1):
            if headings[j]["level"] < h["level"]:
                h["parent_line"] = headings[j]["line_start"]
                break

    return {
        "file": str(file_path.resolve()).replace("\\", "/"),
        "total_lines": total,
        "headings": headings,
    }


def splice_text_at_line(
    file_path: Path, at_line: int, content: str, mode: str = "after"
) -> dict:
    """在指定行号前/后插入 content.

    mode='before' -> content 插入到 at_line 行之前 (become new at_line)
    mode='after'  -> content 插入到 at_line 行之后 (become new at_line+1)
    content 前后空白不裁剪;调用方负责换行符规范化.
    返回 {'file': '...', 'inserted_at': int, 'new_total_lines': int}.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"目标文件不存在: {file_path}")
    if mode not in ("before", "after"):
        raise ValueError(f"mode 必须为 before/after,收到: {mode}")

    original = file_path.read_text(encoding="utf-8")
    if "\r\n" in original:
        eol = "\r\n"
        lines = original.split("\r\n")
    else:
        eol = "\n"
        lines = original.split("\n")
    trailing_eol = bool(lines) and lines[-1] == ""
    if trailing_eol:
        lines = lines[:-1]

    if at_line < 1 or at_line > len(lines) + (1 if mode == "before" else 0):
        raise ValueError(f"at_line {at_line} 超出范围 [1, {len(lines)}]")

    insert_idx = at_line - 1 if mode == "before" else at_line
    new_lines = content.split(eol) if eol in content else content.split("\n")
    lines[insert_idx:insert_idx] = new_lines

    out = eol.join(lines)
    if trailing_eol:
        out += eol
    file_path.write_text(out, encoding="utf-8")

    return {
        "file": str(file_path.resolve()).replace("\\", "/"),
        "inserted_at": at_line if mode == "before" else at_line + 1,
        "new_total_lines": len(lines),
    }


# ============================================================
# workspace root / scan
# ============================================================


def find_workspace_root(cwd: Path) -> Path | None:
    """从 cwd 向上遍历查找含 .mint/workspace.yaml 的目录"""
    cwd = cwd.resolve()
    for d in [cwd, *cwd.parents]:
        if (d / ".mint" / "workspace.yaml").is_file():
            return d
    return None


def scan_meetings(root: Path) -> list[dict]:
    """扫描工作区根下含 meta.yaml 的一级子目录，返回摘要列表

    显式跳过 .mint/ 目录。
    """
    results: list[dict] = []
    if not root.is_dir():
        return results
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name == ".mint":
            continue
        meta_path = child / "meta.yaml"
        if not meta_path.is_file():
            continue
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("扫描会议 %s 失败: %s", child.name, e)
            continue
        stages = meta.get("stages", {}) or {}
        completed = sum(
            1
            for name in STAGE_ORDER
            if (stages.get(name) or {}).get("status") == "completed"
        )
        current = meta.get("current", {}) or {}
        blockers = current.get("blockers") or []
        results.append(
            {
                "dir": child.name,
                "project": meta.get("project", child.name),
                "cursor": current.get("cursor"),
                "progress": f"{completed}/{len(STAGE_ORDER)}",
                "progress_num": completed,
                "last_action": current.get("last_action"),
                "blockers_count": len(blockers),
            }
        )
    return results


# ============================================================
# last_action 双源 max
# ============================================================


def refresh_last_action(meta: dict) -> None:
    """刷新 current.last_action = max(stages.*.completed_at, revisions[*].timestamp)

    无源数据时置 None。ISO 8601 字符串字典序即时间序。
    """
    candidates: list[str] = []
    stages = meta.get("stages", {}) or {}
    for name, stage in stages.items():
        if not isinstance(stage, dict):
            continue
        ts = stage.get("completed_at")
        if ts:
            candidates.append(str(ts))
    for rev in meta.get("revisions", []) or []:
        if not isinstance(rev, dict):
            continue
        ts = rev.get("timestamp")
        if ts:
            candidates.append(str(ts))
    meta.setdefault("current", {})
    meta["current"]["last_action"] = max(candidates) if candidates else None


# ============================================================
# blocker 生命周期
# ============================================================


def add_blocker(meta: dict, blocker: dict) -> None:
    """往 current.blockers 追加一条"""
    meta.setdefault("current", {}).setdefault("blockers", [])
    meta["current"]["blockers"].append(blocker)


def resolve_blockers(meta: dict, predicate: Callable[[dict], bool]) -> list[dict]:
    """移除 predicate 返回 True 的 blocker，返回被移除条目列表"""
    current = meta.setdefault("current", {})
    blockers = current.get("blockers") or []
    kept = []
    removed = []
    for b in blockers:
        if predicate(b):
            removed.append(b)
        else:
            kept.append(b)
    current["blockers"] = kept
    return removed


# ============================================================
# stage / cursor / revision 写入（meta.yaml 单一写入口）
# ============================================================
#
# 这三个 mutator + 对应 CLI 子命令是 meta.yaml 高频字段（stages / current.cursor /
# revisions）的统一写入口，配合 save_meta 的 META_FIELD_ORDER 保序与此处的枚举校验，
# 让 SKILL.md 不必再直接手写 YAML 文本（消除"分脑写入"，见审计 issue
# fix-mint-meta-yaml-split-brain-writing）。


def set_stage(
    meta: dict,
    stage: str,
    status: str,
    version: int | None = None,
    completed_at: str | None = None,
    params: dict | None = None,
    extra_fields: dict | None = None,
) -> dict:
    """设置 stages.<stage> 的状态与附属字段（就地修改 meta，返回该 stage 字典）。

    - stage 必须 ∈ STAGE_ORDER；status 必须 ∈ STATUS_ENUM，否则抛 ValueError
    - status == completed 且未显式给 completed_at 时，自动填 now()（ISO 8601 秒级）
    - params / extra_fields 做浅合并（不覆盖未提及的既有键）
    """
    if stage not in STAGE_ORDER:
        raise ValueError(f"stage 非法: {stage}，必须 ∈ {STAGE_ORDER}")
    if status not in STATUS_ENUM:
        raise ValueError(f"status 非法: {status}，必须 ∈ {STATUS_ENUM}")
    stages = meta.setdefault("stages", {})
    st = stages.get(stage)
    if not isinstance(st, dict):
        st = {}
        stages[stage] = st
    st["status"] = status
    if version is not None:
        st["version"] = version
    if status == "completed" and not completed_at:
        completed_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if completed_at:
        st["completed_at"] = completed_at
    if params:
        merged = dict(st.get("params") or {})
        merged.update(params)
        st["params"] = merged
    if extra_fields:
        for k, v in extra_fields.items():
            st[k] = v
    return st


def set_cursor(meta: dict, cursor: str, desc: str | None = None) -> None:
    """设置 current.cursor（+ 可选 last_action_desc），就地修改 meta。

    cursor 必须 ∈ STAGE_ORDER（流水线阶段）；维护类 skill 不应改 cursor。
    """
    if cursor not in STAGE_ORDER:
        raise ValueError(f"cursor 非法: {cursor}，必须 ∈ {STAGE_ORDER}")
    current = meta.setdefault("current", {})
    current["cursor"] = cursor
    if desc is not None:
        current["last_action_desc"] = desc


def add_revision(
    meta: dict,
    description: str,
    affected_files: list[str] | None = None,
    timestamp: str | None = None,
    rev_type: str | None = None,
) -> dict:
    """往 revisions[] 追加一条修订记录（就地修改 meta，返回新条目）。

    canonical 形态（见 meta-schema.md「revisions」）：
        {timestamp, type(可选), description, affected_files: list}
    timestamp 缺省用 now()（ISO 8601 秒级）；affected_files 缺省 []；
    rev_type 提供时插入 type 字段（取值 patch | revise | sync），缺省不写该键。
    """
    entry: dict[str, Any] = {
        "timestamp": timestamp or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if rev_type:
        entry["type"] = rev_type
    entry["description"] = description
    entry["affected_files"] = list(affected_files or [])
    meta.setdefault("revisions", []).append(entry)
    return entry


# ============================================================
# init_workspace
# ============================================================


def _filter_deliverables(scenario: str, selected: list[str]) -> list[str]:
    """按 scenario 过滤并补齐 deliverables

    interview: 删除 "决议清单"，若无 "精华语录" 则追加
    meeting:   删除 "观点分析"，若无 "问题清单" 则追加
    """
    if scenario == "interview":
        filtered = [d for d in selected if d != "决议清单"]
        if "精华语录" not in filtered:
            filtered.append("精华语录")
        return filtered
    if scenario == "meeting":
        filtered = [d for d in selected if d != "观点分析"]
        if "问题清单" not in filtered:
            filtered.append("问题清单")
        return filtered
    return list(selected)


def init_workspace(
    root: Path, scenario: str, goal: str, deliverables: list[str]
) -> Path:
    """创建 .mint/workspace.yaml

    前置检查：已存在则抛 FileExistsError。
    scenario 非法值抛 ValueError。
    """
    if scenario not in ("interview", "meeting"):
        raise ValueError(f"scenario 值非法: {scenario}")
    ws_path = root / ".mint" / "workspace.yaml"
    if ws_path.exists():
        raise FileExistsError(f"工作区已初始化: {ws_path}")
    filtered = _filter_deliverables(scenario, deliverables)
    ws = {
        "workspace": {
            "name": root.name,
            "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "scenario": scenario,
        },
        "intent": {
            "goal": goal,
            "deliverables": filtered,
        },
    }
    save_workspace(ws_path, ws)
    return ws_path


# ============================================================
# compute_next_hints（规则引擎）
# ============================================================


def _merge_with_workspace(meta: dict, workspace: dict | None) -> dict:
    """返回继承 workspace intent 后的 meta 视图（不修改原 meta）"""
    if not workspace:
        return meta
    intent = dict(meta.get("intent") or {})
    ws_intent = workspace.get("intent") or {}
    ws_root = workspace.get("workspace") or {}
    if not intent.get("goal"):
        intent["goal"] = ws_intent.get("goal", "")
    if not intent.get("deliverables"):
        intent["deliverables"] = list(ws_intent.get("deliverables") or [])
    if not intent.get("scenario"):
        intent["scenario"] = ws_root.get("scenario", "")
    view = dict(meta)
    view["intent"] = intent
    return view


def _first_pending_stage(stages: dict, skip: list[str]) -> str | None:
    for name in STAGE_ORDER:
        if name in skip:
            continue
        st = stages.get(name) or {}
        if st.get("status") == "pending":
            return name
    return None


def _all_completed(stages: dict, skip: list[str]) -> bool:
    for name in STAGE_ORDER:
        if name in skip:
            continue
        st = stages.get(name) or {}
        if st.get("status") != "completed":
            return False
    return True


def compute_next_hints(meta: dict, workspace: dict | None = None) -> dict:
    """按 next-rules.md 推理，返回 {primary, alternatives}

    同时将结果写入 meta.next_hints。
    """
    view = _merge_with_workspace(meta, workspace)
    current = view.get("current") or {}
    blockers = current.get("blockers") or []
    stages = view.get("stages") or {}
    intent = view.get("intent") or {}
    skip = intent.get("skip_stages") or []
    deliverables = intent.get("deliverables") or []
    meeting_dir = view.get("project", "")

    hints: dict[str, Any] = {"primary": {"cmd": "", "reason": ""}, "alternatives": []}

    # Rule 1: blockers 优先
    if blockers:
        first = blockers[0]
        desc = first.get("description", "")
        n = len(blockers)
        hints["primary"] = {
            "cmd": f"/mint:refine {meeting_dir}".strip(),
            "reason": f"当前有 {n} 个阻塞项待处理: {desc}",
        }
        hints["alternatives"] = [
            {"cmd": "/mint:status --detail", "when": "查看全部 blocker 详情"},
        ]
        meta["next_hints"] = hints
        return hints

    # Rule 2: pending 阶段
    pending = _first_pending_stage(stages, skip)
    if pending:
        prev_idx = STAGE_ORDER.index(pending) - 1
        prev_name = STAGE_ORDER[prev_idx] if prev_idx >= 0 else None
        if pending == "transcribe":
            reason = "尚未转录，先将音频转为文字"
        else:
            reason = f"{prev_name} 已完成，建议继续 {pending}"
        alts: list[dict] = []
        if pending == "extract" and "polish" in skip:
            alts.append(
                {"cmd": "/mint:extract --source clean", "when": "跳过 polish 直接结构化"}
            )
        if pending in ("polish", "extract"):
            alts.append({"cmd": "/mint:patch <词>", "when": "发现 ASR 错字需修正"})
        alts.append({"cmd": "/mint:status", "when": "先查看详细进度"})
        hints["primary"] = {
            "cmd": f"/mint:{pending} {meeting_dir}".strip(),
            "reason": reason,
        }
        hints["alternatives"] = alts
        meta["next_hints"] = hints
        return hints

    # Rule 3 / 4: 全部 completed
    if _all_completed(stages, skip):
        # 产物对齐检查（粗粒度：extract 阶段的产物列表若存在，与 deliverables 比对）
        extract_stage = stages.get("extract") or {}
        produced = extract_stage.get("produced") or []
        missing = [d for d in deliverables if d not in produced]
        if missing:
            hints["primary"] = {
                "cmd": f"/mint:extract {meeting_dir}".strip(),
                "reason": f"交付物 {', '.join(missing)} 尚未产出，建议补齐",
            }
            hints["alternatives"] = [
                {"cmd": "/mint:status --detail", "when": "核对产物清单"},
                {"cmd": f"/mint:revise {meeting_dir}".strip(), "when": "通过定向修订调整产物"},
            ]
        else:
            hints["primary"] = {
                "cmd": "",
                "reason": "当前会议已完成全部产出，可进入下一会议或归档",
            }
            hints["alternatives"] = [
                {"cmd": "/mint:next --all", "when": "查看其他会议状态"},
                {"cmd": "/mint:status --detail", "when": "最终产物核查"},
            ]
        meta["next_hints"] = hints
        return hints

    # 兜底
    hints["primary"] = {
        "cmd": "/mint:status",
        "reason": "状态未明确，建议先查看当前进度",
    }
    hints["alternatives"] = []
    meta["next_hints"] = hints
    return hints


def workspace_overall_recommendation(
    meetings: list[dict],
    workspace: dict | None = None,
    workspace_root: Path | None = None,
) -> dict:
    """全景 Rule 5a + Rule 5b：多会议优先级 top-1 推荐

    workspace 参数（可选）：.mint/workspace.yaml 解析后的 dict（顶层含 "workspace" 键）。
    workspace_root 参数（可选）：工作区根路径，用于检查 summarize 产物（汇总分析/mint_*.md）
    是否已生成。未传时退化为不感知产物状态（向后兼容）。
    Rule 5b：scenario == "interview" 且所有会议 progress_num >= 3（polish 及之前完成）且
    会议数 > 0 时——若 summarize 产物未生成则推荐 /mint:summarize；已生成则提示"已完成"，
    alternatives 给重跑或核查质量。
    workspace 为 None 时走原 Rule 5a 逻辑（向后兼容）。
    （注：本规则文档侧见 next-rules.md「Rule 5b」；历史曾称「Rule 6」，与维护类 Rule 6a/6b 撞车，已更名。）
    """
    if not meetings:
        return {"primary": {"cmd": "", "reason": "工作区暂无会议，先运行 /mint:transcribe"}, "alternatives": []}

    # Rule 5b：interview 场景全部 polish 完成 → 推荐 summarize
    if workspace is not None:
        scenario = (workspace.get("workspace") or {}).get("scenario")
        if scenario == "interview" and all(
            (m.get("progress_num") or 0) >= 3 for m in meetings
        ):
            # Rule 5b.1：检查 summarize 产物是否已生成（依赖 workspace_root 注入）
            summary_exists = False
            if workspace_root is not None:
                summary_dir = workspace_root / "汇总分析"
                if summary_dir.is_dir():
                    summary_exists = any(summary_dir.glob("mint_*.md"))

            if summary_exists:
                return {
                    "primary": {
                        "cmd": "",
                        "reason": "全部访谈已 polish 且跨会议汇总产物已生成；可直接消费 汇总分析/ 下的 mint_*.md",
                    },
                    "alternatives": [
                        {
                            "cmd": "/mint:status --workspace --detail",
                            "when": "核查各会议质量评分或回看 blocker",
                        },
                        {
                            "cmd": "/mint:summarize",
                            "when": "想重新生成汇总（旧产物自动备份到 汇总分析/old/）",
                        },
                    ],
                }

            return {
                "primary": {
                    "cmd": "/mint:summarize",
                    "reason": "全部访谈已完成 polish，建议生成跨会议汇总",
                },
                "alternatives": [
                    {
                        "cmd": "/mint:status --workspace --detail",
                        "when": "先核查各会议最终产物",
                    }
                ],
            }

    def sort_key(m: dict) -> tuple:
        # 降序：blockers > 0 / 进度越少 / last_action 越小（None 最小）
        blockers = m.get("blockers_count") or 0
        progress = m.get("progress_num") or 0
        la = m.get("last_action") or ""
        return (-1 if blockers > 0 else 0, progress, la)

    sorted_m = sorted(meetings, key=sort_key)
    top = sorted_m[0]
    reasons = []
    if (top.get("blockers_count") or 0) > 0:
        reasons.append(f"{top['blockers_count']} 个阻塞项待处理")
    if (top.get("progress_num") or 0) < len(STAGE_ORDER):
        reasons.append("进度落后")
    if not top.get("last_action"):
        reasons.append("从未操作")
    reason_text = "、".join(reasons) or "最近活跃"
    return {
        "primary": {
            "cmd": f"/mint:next {top['dir']}",
            "reason": f"优先处理 {top['dir']}: {reason_text}",
        },
        "alternatives": [
            {"cmd": "/mint:status --workspace --detail", "when": "查看全部会议详情"}
        ],
    }


# ============================================================
# CLI
# ============================================================


def _cmd_refresh_last_action(args: argparse.Namespace) -> int:
    meta_path = Path(args.meeting_dir) / "meta.yaml"
    meta = load_meta(meta_path)
    refresh_last_action(meta)
    save_meta(meta_path, meta)
    print(
        json.dumps(
            {"last_action": meta["current"]["last_action"]}, ensure_ascii=False
        )
    )
    return 0


def _cmd_compute_next_hints(args: argparse.Namespace) -> int:
    meta_path = Path(args.meeting_dir) / "meta.yaml"
    meta = load_meta(meta_path)
    workspace = None
    if args.workspace:
        ws_path = Path(args.workspace) / ".mint" / "workspace.yaml"
        if ws_path.exists():
            workspace = load_workspace(ws_path)
    else:
        root = find_workspace_root(Path(args.meeting_dir))
        if root:
            workspace = load_workspace(root / ".mint" / "workspace.yaml")
    meta["project"] = meta.get("project") or Path(args.meeting_dir).name
    hints = compute_next_hints(meta, workspace)
    save_meta(meta_path, meta)
    print(json.dumps(hints, ensure_ascii=False))
    return 0


def _cmd_find_workspace_root(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd or ".").resolve()
    root = find_workspace_root(cwd)
    if root is None:
        return 1
    print(str(root).replace("\\", "/"))
    return 0


def _cmd_scan_meetings(args: argparse.Namespace) -> int:
    root = Path(args.workspace_root)
    meetings = scan_meetings(root)
    print(json.dumps(meetings, ensure_ascii=False))
    return 0


def _cmd_init_workspace(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    deliverables = [d.strip() for d in args.deliverables.split(",") if d.strip()]
    ws_path = init_workspace(root, args.scenario, args.goal, deliverables)
    print(json.dumps({"workspace_yaml": str(ws_path).replace("\\", "/")}, ensure_ascii=False))
    return 0


def _cmd_deliverable_presets(args: argparse.Namespace) -> int:
    """输出 deliverables 预设 single-source（init Q2 选项 + 各场景默认集）。

    供 init/SKILL.md Q2 动态取选项、scenario-presets.md 引用、测试守卫消费。
    """
    print(
        json.dumps(
            {"selectable": DELIVERABLE_SELECTABLE, "presets": DELIVERABLE_PRESETS},
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_normalize_id(args: argparse.Namespace) -> int:
    """按 name 生成规范化 id，与指定注册表的现有 id 去重。

    复用 normalize_id + load_workspace，使 SKILL 层无需内联 python 穿透逻辑层。
    --registry 决定去重命名空间：templates → templates[].id；types → interviewee_types[].id。
    name 含非 ASCII 且不命中 PRESET_TYPE_ID_MAP 时 normalize_id 抛 ValueError → exit 2。
    """
    root = Path(args.workspace_root).resolve()
    ws = load_workspace(root / ".mint" / "workspace.yaml")
    if args.registry == "types":
        source = ws.get("interviewee_types") or []
    else:
        source = ws.get("templates") or []
    existing = {t["id"] for t in source if isinstance(t, dict) and "id" in t}
    new_id = normalize_id(args.name, existing, prefix=args.prefix or "")
    print(json.dumps({"id": new_id}, ensure_ascii=False))
    return 0


def _cmd_validate_meta(args: argparse.Namespace) -> int:
    meta_path = Path(args.meeting_dir) / "meta.yaml"
    validate_meta(meta_path)
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


def _cmd_load_workspace(args: argparse.Namespace) -> int:
    root = Path(args.root)
    ws = load_workspace(root / ".mint" / "workspace.yaml")
    print(json.dumps(ws, ensure_ascii=False))
    return 0


def _cmd_add_blocker(args: argparse.Namespace) -> int:
    meta_path = Path(args.meeting_dir) / "meta.yaml"
    meta = load_meta(meta_path)
    blocker = {
        "type": args.type,
        "description": args.description,
        "suggested_action": args.suggested_action or "",
    }
    add_blocker(meta, blocker)
    save_meta(meta_path, meta)
    print(json.dumps({"added": blocker}, ensure_ascii=False))
    return 0


def _cmd_resolve_blockers(args: argparse.Namespace) -> int:
    meta_path = Path(args.meeting_dir) / "meta.yaml"
    meta = load_meta(meta_path)
    substring = args.substring
    removed = resolve_blockers(
        meta, lambda b: substring in (b.get("description") or "")
    )
    save_meta(meta_path, meta)
    for r in removed:
        logger.info("自动解除 blocker: %s", r.get("description", ""))
    print(json.dumps({"removed": removed}, ensure_ascii=False))
    return 0


# ============================================================
# stage / cursor / revision CLI
# ============================================================


def _coerce_json(value: str) -> Any:
    """优先按 JSON 解析（支持 true/false/数字/对象/数组）；失败则原样字符串。

    便于 CLI 传 `speakers=2`（→ int）/ `desensitized=true`（→ bool）/
    `model=fun-asr`（JSON 解析失败 → 原样 str）。
    """
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


def _parse_kv_list(pairs: list[str] | None) -> dict:
    """把 ['k=v', ...] 解析为 dict，值走 _coerce_json。格式错误抛 ValueError。"""
    out: dict[str, Any] = {}
    for item in pairs or []:
        if "=" not in item:
            raise ValueError(f"参数格式应为 key=value: {item}")
        k, v = item.split("=", 1)
        out[k] = _coerce_json(v)
    return out


def _cmd_set_stage(args: argparse.Namespace) -> int:
    meta_path = Path(args.meeting_dir) / "meta.yaml"
    meta = load_meta(meta_path)
    params = _parse_kv_list(args.param)
    extra = _parse_kv_list(args.field)
    st = set_stage(
        meta,
        args.stage,
        args.status,
        version=args.version,
        completed_at=args.completed_at,
        params=params or None,
        extra_fields=extra or None,
    )
    refresh_last_action(meta)
    save_meta(meta_path, meta)
    print(json.dumps({"stage": args.stage, "value": st}, ensure_ascii=False))
    return 0


def _cmd_set_cursor(args: argparse.Namespace) -> int:
    meta_path = Path(args.meeting_dir) / "meta.yaml"
    meta = load_meta(meta_path)
    set_cursor(meta, args.cursor, desc=args.desc)
    save_meta(meta_path, meta)
    cur = meta.get("current", {})
    print(
        json.dumps(
            {
                "cursor": cur.get("cursor"),
                "last_action_desc": cur.get("last_action_desc"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_add_revision(args: argparse.Namespace) -> int:
    meta_path = Path(args.meeting_dir) / "meta.yaml"
    meta = load_meta(meta_path)
    files = [f.strip() for f in (args.files or "").split(",") if f.strip()]
    entry = add_revision(
        meta,
        args.desc,
        affected_files=files,
        timestamp=args.timestamp,
        rev_type=args.type,
    )
    # 维护类 skill（patch/revise/sync）顺带更新 current.last_action_desc，
    # 但 cursor 停留在最近流水线阶段（见 meta-schema.md current.cursor「stays 语义」）。
    if args.last_action_desc is not None:
        meta.setdefault("current", {})["last_action_desc"] = args.last_action_desc
    refresh_last_action(meta)
    save_meta(meta_path, meta)
    cur = meta.get("current", {})
    print(
        json.dumps(
            {"added": entry, "last_action_desc": cur.get("last_action_desc")},
            ensure_ascii=False,
        )
    )
    return 0


# ============================================================
# types / templates CLI
# ============================================================


def _require_interview_workspace(ws: dict, feature: str) -> None:
    scenario = (ws.get("workspace") or {}).get("scenario")
    if scenario != "interview":
        raise ValueError(f"{feature} 管理仅 interview 场景可用")


def _cmd_types_add(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    ws_path = root / ".mint" / "workspace.yaml"
    ws = load_workspace(ws_path)
    _require_interview_workspace(ws, "types")
    if not ID_PATTERN.match(args.id):
        raise ValueError(
            f"id 非法: {args.id}，必须匹配 ^[a-z][a-z0-9-]*$"
        )
    types = ws.setdefault("interviewee_types", []) or []
    ws["interviewee_types"] = types
    existing_ids = {t["id"] for t in types if isinstance(t, dict) and "id" in t}
    if args.id in existing_ids:
        raise ValueError(f"type id 已存在: {args.id}")
    default_template_id = args.default_template_id
    if default_template_id:
        tpl_ids = {
            t["id"] for t in (ws.get("templates") or []) if isinstance(t, dict)
        }
        if default_template_id not in tpl_ids:
            raise ValueError(
                f"default_template_id {default_template_id} 未在 templates 注册表中"
            )
    new_type = {
        "id": args.id,
        "name": args.name,
        "default_template_id": default_template_id,
    }
    types.append(new_type)
    save_workspace(ws_path, ws)
    print(json.dumps({"added": new_type}, ensure_ascii=False))
    return 0


def _cmd_types_list(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    ws = load_workspace(root / ".mint" / "workspace.yaml")
    types = ws.get("interviewee_types") or []
    usage = scan_meeting_type_usage(root)
    out = []
    for t in types:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        out.append(
            {
                "id": tid,
                "name": t.get("name"),
                "default_template_id": t.get("default_template_id"),
                "meetings_count": len(usage.get(tid, [])),
                "meetings": usage.get(tid, []),
            }
        )
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _cmd_types_remove(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    ws_path = root / ".mint" / "workspace.yaml"
    ws = load_workspace(ws_path)
    types = ws.get("interviewee_types") or []
    if not any(
        isinstance(t, dict) and t.get("id") == args.id for t in types
    ):
        raise ValueError(f"type {args.id} 不存在")
    usage = scan_meeting_type_usage(root)
    refs = usage.get(args.id, [])
    if refs:
        raise ValueError(
            f"type {args.id} 被以下会议引用: {', '.join(refs)}"
        )
    ws["interviewee_types"] = [
        t for t in types if not (isinstance(t, dict) and t.get("id") == args.id)
    ]
    # 从 templates.applies_to 中移除该 type id 引用
    for tpl in ws.get("templates") or []:
        if not isinstance(tpl, dict):
            continue
        applies_to = tpl.get("applies_to") or []
        if args.id in applies_to:
            tpl["applies_to"] = [a for a in applies_to if a != args.id]
    save_workspace(ws_path, ws)
    print(json.dumps({"removed": args.id}, ensure_ascii=False))
    return 0


def _cmd_templates_add(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    ws_path = root / ".mint" / "workspace.yaml"
    ws = load_workspace(ws_path)
    _require_interview_workspace(ws, "templates")
    if not ID_PATTERN.match(args.id):
        raise ValueError(
            f"id 非法: {args.id}，必须匹配 ^[a-z][a-z0-9-]*$"
        )
    templates = ws.setdefault("templates", []) or []
    ws["templates"] = templates
    existing_ids = {
        t["id"] for t in templates if isinstance(t, dict) and "id" in t
    }
    if args.id in existing_ids:
        raise ValueError(f"template id 已存在: {args.id}")
    applies_to = [a.strip() for a in args.applies_to.split(",") if a.strip()]
    if not applies_to:
        raise ValueError("applies_to 不能为空，至少引用 1 个 type id")
    type_ids = {
        t["id"]
        for t in (ws.get("interviewee_types") or [])
        if isinstance(t, dict) and "id" in t
    }
    unknown = [a for a in applies_to if a not in type_ids]
    if unknown:
        raise ValueError(
            f"applies_to 含未注册的 type: {', '.join(unknown)}"
        )

    # 源文件定位：支持绝对路径或相对工作区根的路径
    src_raw = Path(args.file)
    src = src_raw if src_raw.is_absolute() else (root / src_raw)
    src = src.resolve() if src.exists() else src
    if not src.exists() or not src.is_file():
        raise ValueError(f"file not found: {args.file}")

    # 目标路径：.mint/templates/<basename>（保留原文件名，含中文）
    # sanitize 重命名为 <id>.<ext> 由独立升级脚本的 --sanitize flag 处理
    dest_rel = f".mint/templates/{src.name}"
    dest = root / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)

    already_in_place = src.resolve() == dest.resolve()
    if not already_in_place:
        if dest.exists():
            raise ValueError(
                f"目标文件已存在，拒绝覆盖: {dest_rel}"
            )
        shutil.move(str(src), str(dest))

    new_tpl = {
        "id": args.id,
        "name": args.name,
        "file": dest_rel,
        "applies_to": applies_to,
    }
    templates.append(new_tpl)
    updated_types: list[str] = []
    if args.set_default:
        for t in ws.get("interviewee_types") or []:
            if not isinstance(t, dict):
                continue
            if t.get("id") in applies_to:
                t["default_template_id"] = args.id
                updated_types.append(t["id"])
    try:
        save_workspace(ws_path, ws)
    except Exception:
        # workspace 写入失败：若刚搬过文件，回滚避免状态不一致
        if not already_in_place and dest.exists():
            try:
                shutil.move(str(dest), str(src))
            except Exception:
                pass
        raise
    print(
        json.dumps(
            {"added": new_tpl, "updated_types": updated_types},
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_templates_list(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    ws = load_workspace(root / ".mint" / "workspace.yaml")
    templates = ws.get("templates") or []
    out = []
    for t in templates:
        if not isinstance(t, dict):
            continue
        out.append(
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "file": t.get("file"),
                "applies_to": list(t.get("applies_to") or []),
            }
        )
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _cmd_templates_remove(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    ws_path = root / ".mint" / "workspace.yaml"
    ws = load_workspace(ws_path)
    templates = ws.get("templates") or []
    target = next(
        (t for t in templates if isinstance(t, dict) and t.get("id") == args.id),
        None,
    )
    if not target:
        raise ValueError(f"template {args.id} 不存在")
    type_refs = [
        t["id"]
        for t in (ws.get("interviewee_types") or [])
        if isinstance(t, dict) and t.get("default_template_id") == args.id
    ]
    overrides = scan_meeting_template_overrides(root)
    meeting_refs = overrides.get(args.id, [])
    if type_refs or meeting_refs:
        parts = []
        if type_refs:
            parts.append(f"types=[{', '.join(type_refs)}]")
        if meeting_refs:
            parts.append(f"meetings=[{', '.join(meeting_refs)}]")
        raise ValueError(
            f"template {args.id} 被以下引用: {'; '.join(parts)}"
        )
    ws["templates"] = [
        t for t in templates if not (isinstance(t, dict) and t.get("id") == args.id)
    ]
    save_workspace(ws_path, ws)
    file_rel = target.get("file") or ""
    file_path = root / file_rel if file_rel else None
    file_deleted = False
    if file_path and file_path.exists():
        try:
            file_path.unlink()
            file_deleted = True
        except OSError:
            file_deleted = False
    print(
        json.dumps(
            {
                "removed": args.id,
                "file": str(file_path).replace("\\", "/") if file_path else None,
                "file_deleted": file_deleted,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_resolve_template(args: argparse.Namespace) -> int:
    meeting_dir = Path(args.meeting_dir).resolve()
    meta = load_meta(meeting_dir / "meta.yaml")
    root = find_workspace_root(meeting_dir)
    if not root:
        raise ValueError("未找到工作区根")
    ws = load_workspace(root / ".mint" / "workspace.yaml")
    types = ws.get("interviewee_types") or []
    templates = ws.get("templates") or []

    # 分支 A: 显式 --template-override
    if args.template_override:
        tok = args.template_override
        tpl = next(
            (
                t
                for t in templates
                if isinstance(t, dict) and t.get("id") == tok
            ),
            None,
        )
        if tpl:
            file_rel = tpl.get("file") or ""
            result = {
                "template_path": str((root / file_rel).resolve()).replace(
                    "\\", "/"
                ),
                "template_id": tok,
                "source": "explicit",
            }
        else:
            p = Path(tok)
            if not p.is_absolute():
                p = root / p
            if not p.exists():
                raise ValueError(
                    f"template {tok} 不存在于注册表或路径"
                )
            result = {
                "template_path": str(p.resolve()).replace("\\", "/"),
                "template_id": "adhoc",
                "source": "explicit",
            }
        print(json.dumps(result, ensure_ascii=False))
        return 0

    # 分支 B: 按 meta.interviewee_type
    tid = meta.get("interviewee_type")
    if tid:
        t = next(
            (x for x in types if isinstance(x, dict) and x.get("id") == tid),
            None,
        )
        if not t:
            raise ValueError(
                f"类型 {tid} 不存在于 workspace.yaml，请跑 /mint:types list 检查"
            )
        default_tpl_id = t.get("default_template_id")
        if default_tpl_id:
            tpl = next(
                (
                    x
                    for x in templates
                    if isinstance(x, dict) and x.get("id") == default_tpl_id
                ),
                None,
            )
            if not tpl:
                raise ValueError(
                    f"类型 {tid} 的 default_template_id={default_tpl_id} 指向不存在的 template"
                )
            file_rel = tpl.get("file") or ""
            result = {
                "template_path": str((root / file_rel).resolve()).replace(
                    "\\", "/"
                ),
                "template_id": default_tpl_id,
                "source": "type_default",
            }
        else:
            result = {
                "template_path": None,
                "template_id": None,
                "source": "none",
            }
        print(json.dumps(result, ensure_ascii=False))
        return 0

    # 分支 C: 兼容老工作区
    if types:
        raise ValueError(
            "meta.yaml 缺少 interviewee_type 字段。interview 场景下 "
            "interviewee_type 必填，请手工编辑或跑升级脚本"
        )
    result = {"template_path": None, "template_id": None, "source": "none"}
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_summarize_collect(args: argparse.Namespace) -> int:
    root = Path(args.workspace_root).resolve()
    data = collect_summarize_data(root)
    print(json.dumps(data, ensure_ascii=False))
    return 0


def _cmd_summarize_backup_outputs(args: argparse.Namespace) -> int:
    root = Path(args.workspace_root).resolve()
    result = backup_summarize_outputs(root)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_summarize_read_state(args: argparse.Namespace) -> int:
    root = Path(args.workspace_root).resolve()
    state = read_summarize_state(root)
    print(json.dumps(state, ensure_ascii=False))
    return 0


def _cmd_summarize_write_state(args: argparse.Namespace) -> int:
    root = Path(args.workspace_root).resolve()
    raw = sys.stdin.read()
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"stdin JSON 解析失败: {e}")
    result = write_summarize_state(root, state)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_summarize_detect_delta(args: argparse.Namespace) -> int:
    root = Path(args.workspace_root).resolve()
    # v3.0: 可选 --split-mode 参数, 由 SKILL.md 决策后传入
    current_split_mode: bool | None = None
    if getattr(args, "split_mode", None) is not None:
        current_split_mode = args.split_mode
    delta = detect_summarize_delta(root, current_split_mode=current_split_mode)
    print(json.dumps(delta, ensure_ascii=False))
    return 0


def _cmd_summarize_find_anchors(args: argparse.Namespace) -> int:
    p = Path(args.file).resolve()
    result = find_markdown_anchors(p)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_summarize_sha256(args: argparse.Namespace) -> int:
    p = Path(args.file).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"文件不存在: {p}")
    stat = p.stat()
    result = {
        "sha256": sha256_file(p),
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_summarize_splice_text(args: argparse.Namespace) -> int:
    p = Path(args.file).resolve()
    content = sys.stdin.read()
    result = splice_text_at_line(p, args.at_line, content, args.mode)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_workspace_recommendation(args: argparse.Namespace) -> int:
    """全景推荐 CLI：内部调 scan_meetings + load_workspace + workspace_overall_recommendation"""
    root = Path(args.workspace_root).resolve()
    meetings = scan_meetings(root)
    ws_path = root / ".mint" / "workspace.yaml"
    workspace = load_workspace(ws_path) if ws_path.exists() else None
    rec = workspace_overall_recommendation(meetings, workspace, workspace_root=root)
    print(json.dumps(rec, ensure_ascii=False))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meta_io.py",
        description="mint 共享元数据 IO（meta.yaml / workspace.yaml）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("refresh-last-action", help="刷新 current.last_action")
    p.add_argument("meeting_dir")
    p.set_defaults(func=_cmd_refresh_last_action)

    p = sub.add_parser("compute-next-hints", help="计算 next_hints 并写回")
    p.add_argument("meeting_dir")
    p.add_argument("--workspace", default=None, help="显式工作区根路径（可选）")
    p.set_defaults(func=_cmd_compute_next_hints)

    p = sub.add_parser("find-workspace-root", help="向上查找工作区根")
    p.add_argument("cwd", nargs="?", default=None)
    p.set_defaults(func=_cmd_find_workspace_root)

    p = sub.add_parser("scan-meetings", help="扫描工作区会议列表")
    p.add_argument("workspace_root")
    p.set_defaults(func=_cmd_scan_meetings)

    p = sub.add_parser("init-workspace", help="创建 .mint/workspace.yaml")
    p.add_argument("root")
    p.add_argument("scenario")
    p.add_argument("goal")
    p.add_argument("deliverables", help="逗号分隔的 deliverables 列表")
    p.set_defaults(func=_cmd_init_workspace)

    p = sub.add_parser(
        "deliverable-presets",
        help="输出 deliverables 预设 single-source JSON（selectable + presets）",
    )
    p.set_defaults(func=_cmd_deliverable_presets)

    p = sub.add_parser("validate-meta", help="校验 meta.yaml 必填字段")
    p.add_argument("meeting_dir")
    p.set_defaults(func=_cmd_validate_meta)

    p = sub.add_parser("load-workspace", help="读取 workspace.yaml 并输出 JSON")
    p.add_argument("root")
    p.set_defaults(func=_cmd_load_workspace)

    p = sub.add_parser("add-blocker", help="追加一条 blocker")
    p.add_argument("meeting_dir")
    p.add_argument("type", choices=["ambiguity", "missing_input", "user_decision"])
    p.add_argument("description")
    p.add_argument("suggested_action", nargs="?", default="")
    p.set_defaults(func=_cmd_add_blocker)

    p = sub.add_parser("resolve-blockers", help="按 description 子串移除 blocker")
    p.add_argument("meeting_dir")
    p.add_argument("substring")
    p.set_defaults(func=_cmd_resolve_blockers)

    # stage / cursor / revision 单一写入口
    p = sub.add_parser(
        "set-stage", help="设置 stages.<stage> 状态（替代 SKILL 手写 YAML）"
    )
    p.add_argument("meeting_dir")
    p.add_argument("stage", help=f"流水线阶段，∈ {STAGE_ORDER}")
    p.add_argument("--status", required=True, help=f"∈ {STATUS_ENUM}")
    p.add_argument("--version", type=int, default=None)
    p.add_argument(
        "--completed-at",
        dest="completed_at",
        default=None,
        help="ISO8601；status=completed 且不传时自动填 now()",
    )
    p.add_argument(
        "--param",
        action="append",
        default=None,
        help="stages.<stage>.params 的 key=value，可重复（值按 JSON 转型）",
    )
    p.add_argument(
        "--field",
        action="append",
        default=None,
        help="stages.<stage> 顶层附属字段 key=value，可重复（如 desensitized=true）",
    )
    p.set_defaults(func=_cmd_set_stage)

    p = sub.add_parser(
        "set-cursor", help="设置 current.cursor（+ 可选 last_action_desc）"
    )
    p.add_argument("meeting_dir")
    p.add_argument("cursor", help=f"流水线阶段，∈ {STAGE_ORDER}")
    p.add_argument("--desc", default=None, help="current.last_action_desc")
    p.set_defaults(func=_cmd_set_cursor)

    p = sub.add_parser("add-revision", help="往 revisions[] 追加一条修订记录")
    p.add_argument("meeting_dir")
    p.add_argument("--desc", required=True, help="修订描述")
    p.add_argument(
        "--files", default=None, help="逗号分隔的 affected_files 相对路径"
    )
    p.add_argument(
        "--type", default=None, help="修订来源 patch | revise | sync（可选）"
    )
    p.add_argument("--timestamp", default=None, help="ISO8601；缺省 now()")
    p.add_argument(
        "--last-action-desc",
        dest="last_action_desc",
        default=None,
        help="顺带更新 current.last_action_desc（维护类 skill 不改 cursor，仅更新此字段）",
    )
    p.set_defaults(func=_cmd_add_revision)

    # types
    p = sub.add_parser(
        "normalize-id",
        help="按 name 生成规范化 id（与 templates/types 注册表去重）",
    )
    p.add_argument("name")
    p.add_argument("--workspace-root", dest="workspace_root", required=True)
    p.add_argument("--prefix", default="", help="id 前缀，如 tpl-")
    p.add_argument(
        "--registry",
        choices=["templates", "types"],
        default="templates",
        help="去重命名空间，默认 templates",
    )
    p.set_defaults(func=_cmd_normalize_id)

    p = sub.add_parser("types-add", help="添加 interviewee type")
    p.add_argument("root")
    p.add_argument("id")
    p.add_argument("name")
    p.add_argument(
        "--default-template-id",
        default=None,
        dest="default_template_id",
        help="可选：设置默认 template id（必须已存在于 templates 表）",
    )
    p.set_defaults(func=_cmd_types_add)

    p = sub.add_parser("types-list", help="列出 interviewee types + 使用计数")
    p.add_argument("root")
    p.set_defaults(func=_cmd_types_list)

    p = sub.add_parser("types-remove", help="删除 interviewee type（引用完整性检查）")
    p.add_argument("root")
    p.add_argument("id")
    p.set_defaults(func=_cmd_types_remove)

    # templates
    p = sub.add_parser("templates-add", help="添加 template")
    p.add_argument("root")
    p.add_argument("id")
    p.add_argument("name")
    p.add_argument("file", help="相对工作区根的路径（建议 .mint/templates/<id>.ext）")
    p.add_argument("applies_to", help="逗号分隔的 type id 列表")
    p.add_argument(
        "--set-default",
        action="store_true",
        help="同时将该 template 设为 applies_to 中每个 type 的 default_template_id",
    )
    p.set_defaults(func=_cmd_templates_add)

    p = sub.add_parser("templates-list", help="列出 templates")
    p.add_argument("root")
    p.set_defaults(func=_cmd_templates_list)

    p = sub.add_parser(
        "templates-remove", help="删除 template（引用完整性 + 物理文件清理）"
    )
    p.add_argument("root")
    p.add_argument("id")
    p.set_defaults(func=_cmd_templates_remove)

    # resolve-template
    p = sub.add_parser(
        "resolve-template", help="polish 第零步解析 template（三层兜底）"
    )
    p.add_argument("meeting_dir")
    p.add_argument(
        "--template-override",
        default=None,
        dest="template_override",
        help="显式覆盖：template id 或路径",
    )
    p.set_defaults(func=_cmd_resolve_template)

    # summarize
    p = sub.add_parser(
        "summarize-collect",
        help="mint:summarize 数据采集：扫合格会议 + 选 polish 源 + 组装 JSON",
    )
    p.add_argument("workspace_root")
    p.set_defaults(func=_cmd_summarize_collect)

    p = sub.add_parser(
        "summarize-backup-outputs",
        help="mint:summarize 重跑备份：迁移 汇总分析/mint_*.md 到 old/{ts}/",
    )
    p.add_argument("workspace_root")
    p.set_defaults(func=_cmd_summarize_backup_outputs)

    p = sub.add_parser(
        "workspace-recommendation",
        help="mint:next 全景推荐 CLI：scan + load workspace + Rule 5a/5b",
    )
    p.add_argument("workspace_root")
    p.set_defaults(func=_cmd_workspace_recommendation)

    # summarize incremental
    p = sub.add_parser(
        "summarize-read-state",
        help="读取 .summarize-state.json（不存在返回 null）",
    )
    p.add_argument("workspace_root")
    p.set_defaults(func=_cmd_summarize_read_state)

    p = sub.add_parser(
        "summarize-write-state",
        help="写入 .summarize-state.json（state JSON 从 stdin 读入）",
    )
    p.add_argument("workspace_root")
    p.set_defaults(func=_cmd_summarize_write_state)

    p = sub.add_parser(
        "summarize-detect-delta",
        help="对比当前 collect 结果与上次快照，输出 delta JSON",
    )
    p.add_argument("workspace_root")
    # v3.0: 可选 --split-mode true|false, 由 SKILL.md 决策后传入, 触发 split_mode_changed 检测
    p.add_argument(
        "--split-mode",
        type=lambda v: {"true": True, "false": False}[v.lower()],
        default=None,
        help="本次决策的 split_mode (true|false), 用于检测 split_mode_changed",
    )
    p.set_defaults(func=_cmd_summarize_detect_delta)

    p = sub.add_parser(
        "summarize-find-anchors",
        help="解析 Markdown 报告的章节锚点，输出 heading 行号 JSON",
    )
    p.add_argument("file")
    p.set_defaults(func=_cmd_summarize_find_anchors)

    p = sub.add_parser(
        "summarize-sha256",
        help="计算单文件 SHA-256 + size_bytes + mtime",
    )
    p.add_argument("file")
    p.set_defaults(func=_cmd_summarize_sha256)

    p = sub.add_parser(
        "summarize-splice-text",
        help="按行号在文件中 splice 文本（stdin 读入插入内容）",
    )
    p.add_argument("file")
    p.add_argument("--at-line", dest="at_line", type=int, required=True)
    p.add_argument(
        "--mode", choices=["before", "after"], default="after"
    )
    p.set_defaults(func=_cmd_summarize_splice_text)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, ValueError, FileExistsError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
