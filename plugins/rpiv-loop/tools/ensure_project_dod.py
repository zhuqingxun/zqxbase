#!/usr/bin/env python3
"""rpiv-loop DoD 初始化脚本（幂等）。

在 CWD 下创建 rpiv/dod.yaml（若不存在），否则静默跳过。
由 4 入口 SKILL（prime / brainstorm / create-prd / biubiubiu）的
"## 前置初始化" 章节调用。

退出码:
  0 = 已存在（跳过）或成功创建
  1 = 写权限失败 / 模板文件缺失
  2 = 预留给 YAML 解析错误（本脚本不解析，保留兼容）
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent / "dod_template.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="rpiv-loop DoD 初始化")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要执行的动作，不实际写文件",
    )
    args = parser.parse_args()

    cwd = Path.cwd()
    target_dir = cwd / "rpiv"
    target = target_dir / "dod.yaml"

    if not TEMPLATE_PATH.is_file():
        sys.stderr.write(
            "[rpiv-loop] 模板文件缺失\n"
            f"  期望路径: {TEMPLATE_PATH.as_posix()}\n"
            "  请检查插件安装完整性。\n"
        )
        return 1

    if target.is_file():
        sys.stdout.write(f"已存在 rpiv/dod.yaml，跳过（路径: {target.as_posix()}）\n")
        return 0

    if args.dry_run:
        sys.stdout.write(
            f"will create {target.as_posix()} from {TEMPLATE_PATH.as_posix()}\n"
        )
        return 0

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(TEMPLATE_PATH, target)
    except OSError as exc:
        sys.stderr.write(
            "[rpiv-loop] 写入 rpiv/dod.yaml 失败\n"
            f"  目标: {target.as_posix()}\n"
            f"  错误: {exc}\n"
        )
        return 1

    sys.stdout.write(f"已创建 rpiv/dod.yaml（默认模板，路径: {target.as_posix()}）\n")
    sys.stderr.write(
        "[rpiv-loop] 已生成项目级 DoD 模板\n"
        "  请根据项目情况修订 DOD-* 条目（删除不适用项 / 添加项目特有门）。\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
