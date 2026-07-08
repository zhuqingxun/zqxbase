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
import os
import sys
import tempfile
from pathlib import Path

# 复用 flow_status.py 的解析工具（同目录）
sys.path.insert(0, str(Path(__file__).parent))
from flow_status import (  # noqa: E402
    parse_frontmatter,
    classify_file,
    parse_filename,
    is_handoff_name,
    _replace_fm_field,
    AUX_PREFIXES,
    TODO_PREFIXES,
    PROCESS_PREFIXES,
)

ARCHIVABLE_STATUSES = {"completed", "superseded"}
HARD_BLOCK_STATUSES = {"open", "pending"}
SOFT_BLOCK_STATUSES = {"in-progress"}


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
    new_text = _replace_fm_field(text, "status", "archived")
    new_text = _replace_fm_field(new_text, "archived_at", now_iso)
    new_text = _replace_fm_field(new_text, "updated_at", now_iso)

    # 落盘顺序：先把「已打 archived 戳」的内容写进 archive 目录的临时文件，
    # 原子 os.replace 到目标，最后删源文件。任何一步失败都不会出现
    # 「源文件已被标 archived 却没移动」的假完成态（原 write→move 顺序的缺陷）。
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{file_path.stem}.", suffix=".tmp", dir=str(archive_dir)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(new_text)
        os.replace(tmp_name, str(dest_path))
        tmp_name = None  # 已原子替换到目标，无残留临时文件
    except OSError as exc:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass
        # 源文件保持原样（未改、未移），状态一致，无需回滚。
        report["errors"].append({"path": rel, "reason": f"归档写入失败: {exc}"})
        return "error"

    # 目标已就位，删除源文件。删除失败仅留下重复（archive 内已是正确归档版，
    # 源文件仍是未标 archived 的旧内容），仍不构成「标了 archived 没移动」的假完成态。
    try:
        file_path.unlink()
    except OSError as exc:
        report["errors"].append({"path": rel, "reason": f"已写入归档但源文件删除失败: {exc}"})
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
            if any(name.startswith(prefix) for prefix, _ in AUX_PREFIXES) or is_handoff_name(name):
                candidates.append(p)
    return candidates


def collect_feature(rpiv_dir: Path, feature: str) -> list[Path]:
    """收集 feature 名**精确**匹配的文件。

    用 parse_filename 抽取每个文件的真实 feature（剥掉已知前缀后的部分）再精确比对，
    避免 `endswith("-<feature>.md")` 把同尾 feature 误纳入——如 `archive gate` 误匹配
    `prd-rpiv-dod-gate.md`（其真实 feature 是 rpiv-dod-gate）。
    """
    matched: list[Path] = []
    for p in collect_all(rpiv_dir):
        rel_posix = p.relative_to(rpiv_dir.parent).as_posix()
        category = classify_file(rel_posix, p.name)
        _phase, feat = parse_filename(category, p.name)
        if feat == feature:
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
