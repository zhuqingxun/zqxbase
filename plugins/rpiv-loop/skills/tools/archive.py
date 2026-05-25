#!/usr/bin/env python3
"""rpiv-loop:archive 纯程序实现。

支持 3 个 mode:
  /rpiv-loop:archive all              归档所有 status in {completed, superseded}
  /rpiv-loop:archive <feature>        归档 *-<feature>.md 中符合条件者
  /rpiv-loop:archive <path/to/file>   归档单文件

异常退化:
  - status in {open, pending}  → 直接拒绝(exit 1),提示用户先完成
  - status == in-progress     → 默认拒绝,需 --force 强制归档
  - frontmatter 缺失/解析错  → 报告并跳过

零依赖：仅 stdlib + 共享 flow_status.py 的 frontmatter 工具。
"""
from __future__ import annotations

import argparse
import datetime
import re
import shutil
import sys
from pathlib import Path

# 复用 flow_status.py 的解析工具（同目录）
sys.path.insert(0, str(Path(__file__).parent))
from flow_status import (  # noqa: E402
    FRONTMATTER_RE,
    parse_frontmatter,
    classify_file,
    parse_filename,
    AUX_PREFIXES,
    TODO_PREFIXES,
    PROCESS_PREFIXES,
)

ARCHIVABLE_STATUSES = {"completed", "superseded"}
HARD_BLOCK_STATUSES = {"open", "pending"}
SOFT_BLOCK_STATUSES = {"in-progress"}


def _replace_or_insert_fm_field(text: str, key: str, new_value: str) -> str:
    """与 flow_status._replace_fm_field 等价,但本地化以解耦。"""
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


def archive_one(file_path: Path, rpiv_dir: Path, now_iso: str, force: bool,
                report: dict) -> str:
    """对单文件执行归档。返回结果 tag: success / skipped / renamed / error / blocked."""
    file_path = file_path.resolve()
    try:
        rel = file_path.relative_to(rpiv_dir.parent).as_posix()
    except ValueError:
        rel = file_path.as_posix()

    if not file_path.exists():
        report["errors"].append({"path": rel, "reason": "文件不存在"})
        return "error"

    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        report["errors"].append({"path": rel, "reason": f"IO: {exc}"})
        return "error"

    fm = parse_frontmatter(text)
    if fm is None:
        report["errors"].append({"path": rel, "reason": "无 frontmatter,跳过"})
        return "error"

    status = (fm.get("status") or "").strip()

    if status in HARD_BLOCK_STATUSES:
        report["skipped"].append({
            "path": rel, "status": status,
            "reason": f"⛔ 未完成的条目不能归档,请先完成处理并将状态更新为 completed",
        })
        return "blocked"

    if status in SOFT_BLOCK_STATUSES and not force:
        report["skipped"].append({
            "path": rel, "status": status,
            "reason": "in-progress 文件归档需 --force",
        })
        return "blocked"

    if status not in ARCHIVABLE_STATUSES and status not in SOFT_BLOCK_STATUSES:
        # 非标准 status 也阻拦
        report["skipped"].append({
            "path": rel, "status": status or "(空)",
            "reason": f"status={status!r} 非可归档状态",
        })
        return "blocked"

    archive_dir = rpiv_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    dest_name = file_path.name
    dest_path = archive_dir / dest_name
    renamed = False
    if dest_path.exists():
        ts_suffix = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = file_path.stem
        suffix = file_path.suffix
        dest_name = f"{stem}.{ts_suffix}{suffix}"
        dest_path = archive_dir / dest_name
        renamed = True

    # 更新 frontmatter: status=archived, archived_at=now, updated_at=now
    new_text = _replace_or_insert_fm_field(text, "status", "archived")
    new_text = _replace_or_insert_fm_field(new_text, "archived_at", now_iso)
    new_text = _replace_or_insert_fm_field(new_text, "updated_at", now_iso)
    try:
        file_path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        report["errors"].append({"path": rel, "reason": f"写 frontmatter 失败: {exc}"})
        return "error"

    # 移动文件
    try:
        shutil.move(str(file_path), str(dest_path))
    except OSError as exc:
        # 回滚 frontmatter
        try:
            file_path.write_text(text, encoding="utf-8")
        except OSError:
            pass
        report["errors"].append({"path": rel, "reason": f"移动失败: {exc}"})
        return "error"

    if not dest_path.exists():
        report["errors"].append({"path": rel, "reason": "移动后目标不存在"})
        return "error"

    try:
        dest_rel = dest_path.relative_to(rpiv_dir.parent).as_posix()
    except ValueError:
        dest_rel = dest_path.as_posix()
    entry = {
        "path": rel,
        "dest": dest_rel,
        "filename": file_path.name,
        "created_at": fm.get("created_at"),
        "archived_at": now_iso,
        "status_before": status,
    }
    if renamed:
        entry["renamed_to"] = dest_name
        report["renamed"].append(entry)
    report["success"].append(entry)
    return "renamed" if renamed else "success"


def collect_all(rpiv_dir: Path) -> list[Path]:
    """收集所有可能归档的 live 文件(不含 archive/)."""
    candidates: list[Path] = []
    for sub in ("requirements", "plans", "validation", "todo"):
        d = rpiv_dir / sub
        if d.is_dir():
            candidates.extend(p for p in d.iterdir() if p.is_file() and p.suffix == ".md")
    for p in rpiv_dir.iterdir():
        if p.is_file() and p.suffix == ".md":
            name = p.name
            if any(name.startswith(prefix) for prefix, _ in AUX_PREFIXES) or name.startswith("handoff-"):
                candidates.append(p)
    return candidates


def collect_feature(rpiv_dir: Path, feature: str) -> list[Path]:
    """收集 *-<feature>.md 命名模式的文件。"""
    matched: list[Path] = []
    target_suffix = f"-{feature}.md"
    all_files = collect_all(rpiv_dir)
    for p in all_files:
        name = p.name
        # 1. 任何前缀 + -feature.md
        if name.endswith(target_suffix):
            matched.append(p)
            continue
        # 2. 裸名(无前缀的 todo)
        if p.parent.name == "todo" and p.stem == feature:
            matched.append(p)
    return matched


def print_report(report: dict) -> int:
    """打印归档报告;返回 exit code(success>0 即 0)。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"## 归档报告 - {now}\n")

    n_success = len(report["success"])
    n_skipped = len(report["skipped"])
    n_renamed = len(report["renamed"])
    n_errors = len(report["errors"])

    if n_success:
        print(f"### 成功归档 ({n_success} 个文件)\n")
        for e in report["success"]:
            print(f"- [ archived ] {e['filename']}")
            print(f"  - 原路径: {e['path']}")
            print(f"  - 归档路径: {e['dest']}")
            if e.get("created_at"):
                print(f"  - 创建时间: {e['created_at']}")
            print(f"  - 归档时间: {e['archived_at']}")
            if e.get("renamed_to"):
                print(f"  - 已重命名: {e['renamed_to']}（原归档目录已有同名文件）")
        print()

    if n_skipped:
        print(f"### 跳过的文件 ({n_skipped} 个)\n")
        for e in report["skipped"]:
            print(f"- [ {e['status']} ] {e['path']}")
            print(f"  - 原因: {e['reason']}")
        print()

    if n_errors:
        print(f"### 错误 ({n_errors} 个)\n")
        for e in report["errors"]:
            print(f"- [ error ] {e['path']}")
            print(f"  - 错误: {e['reason']}")
        print()

    print(f"---\n总计: 成功 {n_success} | 跳过 {n_skipped} | 重命名 {n_renamed} | 错误 {n_errors}")
    return 0 if n_errors == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="rpiv-loop:archive (Python)")
    parser.add_argument("target", help="归档目标: all | <feature-name> | <path/to/file.md>")
    parser.add_argument("--rpiv-dir", default=None, help="rpiv 目录绝对路径,默认 ./rpiv")
    parser.add_argument("--force", action="store_true", help="允许归档 in-progress 文件")
    parser.add_argument("--dry-run", action="store_true", help="不实际移动文件,仅打印计划")
    args = parser.parse_args()

    cwd = Path.cwd()
    rpiv_dir = (Path(args.rpiv_dir) if args.rpiv_dir else cwd / "rpiv").resolve()
    if not rpiv_dir.is_dir():
        print(f"❌ rpiv/ 目录不存在: {rpiv_dir}", file=sys.stderr)
        return 2

    now_iso = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    report: dict = {"success": [], "skipped": [], "renamed": [], "errors": []}

    target = args.target.strip()

    if target == "all":
        candidates = collect_all(rpiv_dir)
    elif "/" in target or target.endswith(".md") or "\\" in target:
        # 单文件路径模式
        candidate = Path(target) if Path(target).is_absolute() else (cwd / target).resolve()
        if not candidate.exists():
            alt = (rpiv_dir.parent / target).resolve()
            if alt.exists():
                candidate = alt
        if not candidate.exists():
            print(f"❌ 文件不存在: {target}", file=sys.stderr)
            return 1
        candidates = [candidate]
    else:
        candidates = collect_feature(rpiv_dir, target)
        if not candidates:
            print(f"❌ 未找到 feature '{target}' 相关文件", file=sys.stderr)
            return 1

    if args.dry_run:
        print(f"## Dry-run 计划 ({len(candidates)} 个候选)\n")
        for p in candidates:
            rel = p.relative_to(rpiv_dir.parent).as_posix() if p.is_relative_to(rpiv_dir.parent) else str(p)
            try:
                text = p.read_text(encoding="utf-8")
                fm = parse_frontmatter(text)
                st = (fm or {}).get("status", "?")
            except OSError:
                st = "(IO 错误)"
            verdict = "✓" if st in ARCHIVABLE_STATUSES else (
                "⚠️ 需 --force" if st in SOFT_BLOCK_STATUSES else "⛔"
            )
            print(f"{verdict} [{st}] {rel}")
        return 0

    for p in candidates:
        archive_one(p, rpiv_dir, now_iso, args.force, report)

    return print_report(report)


if __name__ == "__main__":
    sys.exit(main())
