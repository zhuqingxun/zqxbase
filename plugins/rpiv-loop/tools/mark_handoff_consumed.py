#!/usr/bin/env python3
"""Atomically mark a handoff as consumed and move it to archive."""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from flow_status import _replace_fm_field, parse_frontmatter  # noqa: E402


def unique_dest(path: Path) -> Path:
    if not path.exists():
        return path
    suffix = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}.{suffix}{path.suffix}")


def mark_consumed(path: Path, now_iso: str, dry_run: bool = False) -> Path:
    source = path.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"文件不存在: {source}")

    text = source.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    if fm is None:
        raise ValueError("handoff 文件缺少 frontmatter")

    status = (fm.get("status") or "").strip()
    if status != "pending":
        raise ValueError(f"status={status!r} 不在预期范围 pending")

    handoff_dir = source.parent
    archive_dir = handoff_dir / "archive"
    dest = unique_dest(archive_dir / source.name)

    updated = _replace_fm_field(text, "status", "archived")
    updated = _replace_fm_field(updated, "consumed_at", now_iso)
    updated = _replace_fm_field(updated, "archived_at", now_iso)
    updated = _replace_fm_field(updated, "updated_at", now_iso)

    if dry_run:
        return dest

    archive_dir.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{source.stem}.", suffix=".tmp", dir=str(archive_dir)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(updated)
        os.replace(tmp_name, dest)
        tmp_name = None
        source.unlink()
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.remove(tmp_name)

    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="mark handoff consumed")
    parser.add_argument("path", help="handoff markdown path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now_iso = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        dest = mark_consumed(Path(args.path), now_iso, dry_run=args.dry_run)
    except Exception as exc:
        print(f"⛔ {exc}", file=sys.stderr)
        return 1

    action = "dry-run: 将归档到" if args.dry_run else "✅ 已消费并归档到"
    print(f"{action} {dest.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
