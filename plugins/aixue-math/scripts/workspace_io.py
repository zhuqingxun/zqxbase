# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""workspace_io.py — aixue-math 插件共享工作区元数据 IO 模块

集中实现：
- workspace.yaml 的读写（保序）
- 基础状态更新（inputs / outputs 各字段）
- find_workspace_root：从 cwd 往上找 .aixue/workspace.yaml

CLI 子命令（供 SKILL.md Bash 调用）:
    init-workspace <workspace_root> <name> <grade> <textbook_edition>
                   [--title T] [--unit U] [--lesson-type L] [--shared-dir D]
    next-seq <workspaces_dir> [--name 课题名]
    load-workspace <workspace_root>
    find-workspace-root [cwd]
    update-input <workspace_root> <input_name> <key=value> ...
    update-output <workspace_root> <key=value> ...
    add-revision <workspace_root> <description> <file1,file2,...>

JSON 输出均使用 ensure_ascii=False 保留中文。
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Any

import yaml

LESSON_FILE_RE = re.compile(r"^v(\d+)-课时(\d+)-")
LESSON_FMTS = ("md", "docx", "html", "pdf")

# 课题目录序号前缀：workspaces/ 与 _dist/ 下的课题目录统一叫 `NN_<课题名>`
# （例 `01_周长_什么是周长`），序号只做文件管理器里的排序/索引，
# 不进 workspace.yaml 的 `name`（那里存去掉前缀的纯课题名）。
SEQ_PREFIX_RE = re.compile(r"^(\d{2,})_(.+)$")

WORKSPACE_FIELD_ORDER = [
    "workspace",
    "inputs",
    "outputs",
    "revisions",
    "current",
    "next_hints",
]

VALID_INPUT_NAMES = ["textbook", "knowledge", "guidelines", "samples"]
VALID_INPUT_STATUS = {
    "textbook": {"pending", "extracted", "verified"},
    "knowledge": {"pending", "extracted", "verified"},
    "guidelines": {"ref_only", "customized"},
    "samples": {"ref_only", "customized"},
}
VALID_OUTPUT_STATUS = {"pending", "draft", "final"}
VALID_LESSON_STATUS = {"pending", "draft", "reviewed", "final"}


def ordered_dump(data: dict, path: Path) -> None:
    """按字段顺序写入 YAML，保留 Unicode、不用字母序。"""
    ordered = {k: data[k] for k in WORKSPACE_FIELD_ORDER if k in data}
    for k in data:
        if k not in ordered:
            ordered[k] = data[k]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            ordered, f, allow_unicode=True, sort_keys=False, default_flow_style=False
        )


def load_workspace(root: Path) -> dict:
    yaml_path = root / ".aixue" / "workspace.yaml"
    if not yaml_path.is_file():
        raise FileNotFoundError(f"{yaml_path} 不存在；请先运行 aixue-math:init")
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for field in ["workspace", "inputs", "outputs", "current", "next_hints"]:
        if field not in data:
            raise KeyError(f"workspace.yaml 缺少必要字段 {field}")
    return data


def save_workspace(root: Path, data: dict) -> None:
    yaml_path = root / ".aixue" / "workspace.yaml"
    ordered_dump(data, yaml_path)


def strip_seq_prefix(dir_name: str) -> str:
    """`01_周长_什么是周长` → `周长_什么是周长`；无前缀则原样返回。"""
    m = SEQ_PREFIX_RE.match(dir_name)
    return m.group(2) if m else dir_name


def next_workspace_seq(workspaces_dir: Path, width: int = 2) -> str:
    """扫描 workspaces/ 下已有的 `NN_` 前缀，返回下一个可用序号（补零字符串）。

    只认目录（不看文件），空目录或全无前缀时返回 `01`。序号按创建先后
    单调追加：新课题永远排在末尾，不重排既有编号。
    """
    used: list[int] = []
    if workspaces_dir.is_dir():
        for d in workspaces_dir.iterdir():
            if not d.is_dir():
                continue
            m = SEQ_PREFIX_RE.match(d.name)
            if m:
                used.append(int(m.group(1)))
    nxt = max(used) + 1 if used else 1
    return str(nxt).zfill(width)


def build_initial_workspace(
    name: str,
    grade: str,
    textbook_edition: str,
    title: str | None = None,
    unit: str | None = None,
    lesson_type: str = "新授课",
    shared_dir: str = "../../shared",
    dist_dir: str | None = None,
    dir_name: str | None = None,
) -> dict:
    # 成品输出根：docx/pdf/html/png 等可重建产物一律落在仓库根 _dist/<课题>/，
    # 不与 workspace 内的源文件混放，也不入 git（便于整包传递给协作者）。
    # 用 **workspace 目录名**（含 `NN_` 序号前缀）而非 name 命名，好让 _dist/
    # 与 workspaces/ 目录一一镜像 —— render_boards.py 等脚本正是按目录名推导
    # 成品路径的（`DIST_ROOT / ws.name`）。
    if dist_dir is None:
        dist_dir = f"../../_dist/{dir_name or name}"
    return {
        "workspace": {
            "name": name,
            "title": title or name,
            "grade": grade,
            "subject": "数学",
            "textbook_edition": textbook_edition,
            "unit": unit or "",
            "lesson_type": lesson_type,
            "duration_minutes": 40,
            "created": date.today().isoformat(),
            "shared_dir": shared_dir,
            "dist_dir": dist_dir,
        },
        "inputs": {
            "textbook": {
                "status": "pending",
                "source_pdf": None,
                "pdf_pages": None,
                "book_pages": None,
                "extracted_at": None,
                "extracted_md": None,
            },
            "knowledge": {
                "status": "pending",
                "source": None,
                "extracted_md": None,
            },
            "guidelines": {
                "status": "ref_only",
                "ref_path": f"{shared_dir}/03_写作要求/",
            },
            "samples": {
                "status": "ref_only",
                "ref_path": f"{shared_dir}/04_教案样例/",
            },
        },
        "outputs": {
            "lesson_plan": {
                "status": "pending",
                "draft_md": None,
                "final_md": None,
                "version": 0,
                "generated_at": None,
            },
            "lessons": {},
        },
        "revisions": [],
        "current": {
            "cursor": None,
            "last_action": None,
            "last_action_desc": None,
            "blockers": [],
        },
        "next_hints": {
            "primary": {
                "cmd": "/aixue-math:textbook",
                "reason": "工作区已初始化，下一步是提取教材 (输入 1)",
            },
            "alternatives": [],
        },
    }


def create_dir_link(link_path: Path, target: Path) -> tuple[bool, str]:
    """创建指向 target 的目录链接。

    Windows 用 junction (mklink /J)，Unix 用 symlink。
    返回 (成功?, 方法或失败原因)。若 link_path 已存在/已是链接则视为成功。
    """
    if link_path.is_symlink() or link_path.exists():
        return True, "already exists"

    target_abs = str(target.resolve())
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link_path), target_abs],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return False, f"mklink failed: {result.stderr.strip() or result.stdout.strip()}"
            return True, "junction"
        else:
            link_path.symlink_to(target_abs, target_is_directory=True)
            return True, "symlink"
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"exception: {e}"


def create_dir_skeleton(root: Path, shared_dir: str) -> dict:
    """创建 workspace 的目录骨架，并把 03_/04_ 链接到 shared 资源。

    返回 linking 结果字典，供 init-workspace 输出报告用。
    """
    # 1) 基础目录 —— 只建「源」目录。
    #    2026-08-07 起：docx/html/pdf 等成品归 _dist/<课题>/（见 workspace.dist_dir），
    #    不在 workspace 内创建；01/02 的 docs/ 也不再建（新规范：教材教参一律用
    #    source_pdf 相对路径引用 RAW_DATA，不复制副本进 workspace）。
    subdirs = [
        ".aixue",
        "01_教材/extracted",
        "02_知识点/extracted",
        "05_教案/md",
        "06_板书",
    ]
    for sd in subdirs:
        (root / sd).mkdir(parents=True, exist_ok=True)

    # 2) 解析 shared 绝对路径
    if Path(shared_dir).is_absolute():
        shared_abs = Path(shared_dir).resolve()
    else:
        shared_abs = (root / shared_dir).resolve()

    # 3) 确保 shared 下目标目录存在（不存在则创建空目录占位）
    shared_guidelines = shared_abs / "03_写作要求"
    shared_samples = shared_abs / "04_教案样例"
    shared_guidelines.mkdir(parents=True, exist_ok=True)
    shared_samples.mkdir(parents=True, exist_ok=True)

    # 4) 建立链接；失败则 fallback 为普通目录 + README 说明
    link_report = {}
    for name, target in [
        ("03_写作要求", shared_guidelines),
        ("04_教案样例", shared_samples),
    ]:
        link_path = root / name
        ok, how = create_dir_link(link_path, target)
        if ok:
            link_report[name] = {"linked": True, "method": how, "target": str(target)}
        else:
            # fallback：创建普通目录 + README 说明预期引用 shared
            link_path.mkdir(parents=True, exist_ok=True)
            readme = link_path / "README.md"
            if not readme.exists():
                readme.write_text(
                    f"# {name}\n\n"
                    f"> ⚠ 目录链接创建失败（原因：{how}），此目录已回退为普通目录。\n\n"
                    f"本目录预期链接到全局共享资源：\n\n"
                    f"`{target}`\n\n"
                    f"可选恢复方式：\n\n"
                    f"1. 以管理员身份重新运行 aixue-math:init；\n"
                    f"2. 手动建立 junction：`cmd /c mklink /J \"{link_path}\" \"{target}\"`；\n"
                    f"3. 保持现状：在本目录放置课时专属内容（此时 workspace.yaml 的对应 status 改为 customized）。\n",
                    encoding="utf-8",
                )
            link_report[name] = {"linked": False, "method": how, "target": str(target)}

    return link_report


def find_workspace_root(cwd: Path) -> Path | None:
    """从 cwd 向上查找含 .aixue/workspace.yaml 的目录。"""
    current = cwd.resolve()
    while current != current.parent:
        if (current / ".aixue" / "workspace.yaml").is_file():
            return current
        current = current.parent
    return None


def parse_kv_pairs(pairs: list[str]) -> dict:
    out = {}
    for p in pairs:
        if "=" not in p:
            raise ValueError(f"无效键值对: {p}（期望 key=value）")
        k, v = p.split("=", 1)
        out[k.strip()] = v.strip() if v != "null" else None
    return out


# ============ CLI 子命令 ============


def cmd_init_workspace(args):
    root = Path(args.workspace_root).resolve()
    yaml_path = root / ".aixue" / "workspace.yaml"
    if yaml_path.is_file():
        print(f"ERROR: 工作区已初始化: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    data = build_initial_workspace(
        name=args.name,
        grade=args.grade,
        textbook_edition=args.textbook_edition,
        title=args.title,
        unit=args.unit,
        lesson_type=args.lesson_type,
        shared_dir=args.shared_dir,
        dist_dir=args.dist_dir,
        dir_name=root.name,
    )
    link_report = create_dir_skeleton(root, args.shared_dir)
    save_workspace(root, data)

    print(
        json.dumps(
            {
                "workspace_yaml": str(yaml_path),
                "workspace_root": str(root),
                "shared_links": link_report,
            },
            ensure_ascii=False,
        )
    )


def cmd_next_seq(args):
    """给新课题分配序号；传 --name 时顺带拼出目录名与 dist_dir。"""
    ws_dir = Path(args.workspaces_dir).resolve()
    seq = next_workspace_seq(ws_dir, width=args.width)
    out: dict[str, Any] = {"seq": seq, "workspaces_dir": str(ws_dir)}
    if args.name:
        pure = strip_seq_prefix(args.name)  # 用户误带前缀时先剥掉，避免 01_01_xxx
        out["name"] = pure
        out["dir_name"] = f"{seq}_{pure}"
        out["workspace_root"] = str(ws_dir / out["dir_name"])
        out["dist_dir"] = f"../../_dist/{out['dir_name']}"
    print(json.dumps(out, ensure_ascii=False))


def cmd_load_workspace(args):
    root = Path(args.workspace_root).resolve()
    data = load_workspace(root)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def cmd_find_workspace_root(args):
    cwd = Path(args.cwd or ".").resolve()
    root = find_workspace_root(cwd)
    if root is None:
        print("ERROR: 未找到 aixue-math 工作区（向上查找 .aixue/workspace.yaml 失败）", file=sys.stderr)
        sys.exit(1)
    print(str(root))


def cmd_update_input(args):
    root = Path(args.workspace_root).resolve()
    if args.input_name not in VALID_INPUT_NAMES:
        print(f"ERROR: 无效输入名 {args.input_name}，应为 {VALID_INPUT_NAMES}", file=sys.stderr)
        sys.exit(1)

    data = load_workspace(root)
    updates = parse_kv_pairs(args.kv)

    if "status" in updates:
        allowed = VALID_INPUT_STATUS[args.input_name]
        if updates["status"] not in allowed:
            print(
                f"ERROR: status={updates['status']} 无效，{args.input_name} 允许 {allowed}",
                file=sys.stderr,
            )
            sys.exit(1)

    data["inputs"][args.input_name].update(updates)
    save_workspace(root, data)
    print(json.dumps({"updated": args.input_name, "fields": list(updates.keys())}, ensure_ascii=False))


def cmd_update_output(args):
    root = Path(args.workspace_root).resolve()
    data = load_workspace(root)
    updates = parse_kv_pairs(args.kv)

    if "status" in updates and updates["status"] not in VALID_OUTPUT_STATUS:
        print(
            f"ERROR: status={updates['status']} 无效，应为 {VALID_OUTPUT_STATUS}",
            file=sys.stderr,
        )
        sys.exit(1)

    data["outputs"]["lesson_plan"].update(updates)
    save_workspace(root, data)
    print(json.dumps({"updated": "lesson_plan", "fields": list(updates.keys())}, ensure_ascii=False))


def cmd_upsert_lesson(args):
    """新增或更新 outputs.lessons[<num>] 条目，支持多课时 workspace。"""
    root = Path(args.workspace_root).resolve()
    data = load_workspace(root)
    updates = parse_kv_pairs(args.kv)

    data["outputs"].setdefault("lessons", {})
    key = str(args.lesson_num)
    entry = data["outputs"]["lessons"].get(key, {
        "title": None,
        "current_version": 0,
        "md": None,
        "docx": None,
        "html": None,
        "pdf": None,
        "generated_at": None,
    })
    entry.update(updates)
    data["outputs"]["lessons"][key] = entry
    save_workspace(root, data)
    print(json.dumps(
        {"upserted_lesson": key, "fields": list(updates.keys()), "entry": entry},
        ensure_ascii=False,
    ))


def resolve_dist_root(root: Path) -> Path:
    """解析成品输出根：取 workspace.dist_dir（相对 workspace 根解析），
    缺省回退 ../../_dist/<课题名>。"""
    d = None
    try:
        d = (load_workspace(root).get("workspace") or {}).get("dist_dir")
    except Exception:
        pass
    if not d:
        d = f"../../_dist/{root.name}"
    p = Path(d)
    return p if p.is_absolute() else (root / p).resolve()


def cmd_rotate_versions(args):
    """把每课时的非最新版本降级到 OLD/。幂等。

    2026-08-07 起源与成品分离：
      md（源）      workspace/05_教案/md/
      docx/html/pdf  dist/05_教案/<fmt>/
    两侧的历史版本一律降级到 **dist** 的 05_教案/OLD/<fmt>/ —— 历史版属
    「可重建 / 可从 git 历史找回」的内容，不入库，故统一放在不入库的 dist 侧。
    """
    root = Path(args.workspace_root).resolve()
    dist = resolve_dist_root(root)
    old_base = dist / "05_教案" / "OLD"
    moved = []
    for fmt in LESSON_FMTS:
        # md 是源，留在 workspace；其余格式是成品，在 dist
        src = (root / "05_教案" / fmt) if fmt == "md" else (dist / "05_教案" / fmt)
        if not src.is_dir():
            continue
        by_lesson: dict[str, list[tuple[int, Path]]] = {}
        for f in src.glob(f"*.{fmt}"):
            m = LESSON_FILE_RE.match(f.name)
            if not m:
                continue
            by_lesson.setdefault(m.group(2), []).append((int(m.group(1)), f))
        for items in by_lesson.values():
            latest = max(v for v, _ in items)
            for ver, f in items:
                if ver != latest:
                    dst = old_base / fmt / f.name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(dst))
                    try:
                        rel = str(dst.relative_to(root.parent.parent))
                    except ValueError:
                        rel = str(dst)
                    moved.append(rel.replace("\\", "/"))
    print(json.dumps({"rotated_to_old": moved}, ensure_ascii=False))


def cmd_add_revision(args):
    root = Path(args.workspace_root).resolve()
    data = load_workspace(root)
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "description": args.description,
        "affected_files": args.files.split(",") if args.files else [],
    }
    data["revisions"].append(entry)
    save_workspace(root, data)
    print(json.dumps({"added_revision": entry}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="workspace_io.py", description="aixue-math workspace.yaml IO")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-workspace", help="创建新工作区")
    p_init.add_argument("workspace_root")
    p_init.add_argument("name", help="课时名")
    p_init.add_argument("grade", help="年级，如 '三年级下册'")
    p_init.add_argument("textbook_edition", help="教材版本，如 '北师大版'")
    p_init.add_argument("--title", default=None, help="实际课题（默认同 name）")
    p_init.add_argument("--unit", default=None, help="所属单元")
    p_init.add_argument("--lesson-type", default="新授课")
    p_init.add_argument("--shared-dir", default="../../shared", help="全局共享资源路径")
    p_init.add_argument("--dist-dir", default=None, help="成品输出根（docx/pdf/html/png），默认 ../../_dist/<工作区目录名>")
    p_init.set_defaults(func=cmd_init_workspace)

    p_seq = sub.add_parser("next-seq", help="给新课题分配 workspaces/ 下的下一个序号前缀")
    p_seq.add_argument("workspaces_dir", help="workspaces/ 目录路径")
    p_seq.add_argument("--name", default=None, help="课题名（不含序号）；给了就一并返回 dir_name / workspace_root / dist_dir")
    p_seq.add_argument("--width", type=int, default=2, help="序号位数，默认 2（01、02…）")
    p_seq.set_defaults(func=cmd_next_seq)

    p_load = sub.add_parser("load-workspace", help="读取 workspace.yaml 返回 JSON")
    p_load.add_argument("workspace_root")
    p_load.set_defaults(func=cmd_load_workspace)

    p_find = sub.add_parser("find-workspace-root", help="向上查找工作区根")
    p_find.add_argument("cwd", nargs="?", default=None)
    p_find.set_defaults(func=cmd_find_workspace_root)

    p_ui = sub.add_parser("update-input", help="更新某 input 的状态/字段")
    p_ui.add_argument("workspace_root")
    p_ui.add_argument("input_name", choices=VALID_INPUT_NAMES)
    p_ui.add_argument("kv", nargs="+", help="key=value 对")
    p_ui.set_defaults(func=cmd_update_input)

    p_uo = sub.add_parser("update-output", help="更新 outputs.lesson_plan 字段")
    p_uo.add_argument("workspace_root")
    p_uo.add_argument("kv", nargs="+", help="key=value 对")
    p_uo.set_defaults(func=cmd_update_output)

    p_ul = sub.add_parser("upsert-lesson", help="新增或更新某课时的产出条目")
    p_ul.add_argument("workspace_root")
    p_ul.add_argument("lesson_num", help="课时号（1, 2, 3, ...）")
    p_ul.add_argument("kv", nargs="+", help="key=value 对")
    p_ul.set_defaults(func=cmd_upsert_lesson)

    p_rot = sub.add_parser("rotate-versions", help="每课时非最新版本降级到 05_教案/OLD/")
    p_rot.add_argument("workspace_root")
    p_rot.set_defaults(func=cmd_rotate_versions)

    p_rev = sub.add_parser("add-revision", help="追加修订记录")
    p_rev.add_argument("workspace_root")
    p_rev.add_argument("description")
    p_rev.add_argument("files", help="逗号分隔的文件路径")
    p_rev.set_defaults(func=cmd_add_revision)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
