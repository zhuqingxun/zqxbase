#!/usr/bin/env python3
"""rpiv-loop AC gate PostToolUse hook。

对 Write/Edit/MultiEdit 到 `rpiv/validation/delivery-report-*.md` 或
`rpiv/validation/<feature>/delivery-report.md` 的操作做事后校验：
若 acceptance.yaml 中 blocking AC 未达标，退出码 2 + stderr 提示，
让 Claude 立即撤销/修复，无法"美化式"放行交付报告。

规范来源: prd-rpiv-dod-gate §7 场景 4 Layer 3

Hook 协议:
  stdin: Claude Code 注入的 JSON payload {tool_name, tool_input, ...}
  退出码 0 = 放行；退出码 2 + stderr = 阻止，反馈给 Claude
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CHECK_SCRIPT = (
    Path(__file__).resolve().parent.parent / "tools" / "check_acceptance.py"
)


def extract_feature(posix: str) -> str | None:
    """从 delivery-report 文件路径提取 feature 名。

    支持两种形式：
      rpiv/validation/<feature>/delivery-report.md      -> <feature>
      rpiv/validation/delivery-report-<feature>.md      -> <feature>
    """
    name = Path(posix).name
    if not posix.endswith(".md"):
        return None
    if "/rpiv/validation/" not in posix:
        return None
    # 扁平形式 delivery-report-<feature>.md
    if name.startswith("delivery-report-") and name.endswith(".md"):
        return name[len("delivery-report-"):-len(".md")]
    # 子目录形式 <feature>/delivery-report.md
    if name == "delivery-report.md":
        parent = Path(posix).parent.name
        if parent and parent != "validation":
            return parent
    return None


def derive_project_root(file_path: str) -> Path | None:
    """从 file_path 上溯找到 rpiv 目录的父目录作为项目根。

    hook 进程的默认 CWD 不是用户项目根，必须从 file_path 推导。
    check_acceptance.py 用 Path.cwd() 查找 rpiv/validation/...，
    故 subprocess 必须传 cwd=project_root。
    """
    try:
        p = Path(file_path).resolve()
    except (OSError, ValueError):
        return None
    for ancestor in [p, *p.parents]:
        if ancestor.name == "rpiv":
            return ancestor.parent
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # stdin 解析失败 -> 静默放行，避免 hook bug 阻塞用户
        return 0

    if payload.get("tool_name") not in {"Write", "Edit", "MultiEdit"}:
        return 0

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0

    posix = Path(file_path).as_posix()
    feature = extract_feature(posix)
    if feature is None:
        return 0  # 非 delivery-report，放行

    if not CHECK_SCRIPT.is_file():
        sys.stderr.write(
            "[rpiv-loop] check_acceptance.py 缺失\n"
            f"  期望路径: {CHECK_SCRIPT.as_posix()}\n"
            "  降级放行（请检查插件安装完整性）。\n"
        )
        return 0

    project_root = derive_project_root(file_path)
    if project_root is None:
        # file_path 无法上溯到 rpiv 目录 -> 降级放行
        sys.stderr.write(
            "[rpiv-loop] 无法从 file_path 推导项目根（未找到 rpiv 上溯祖先）\n"
            f"  file_path: {posix}\n"
            "  降级放行。\n"
        )
        return 0

    try:
        result = subprocess.run(
            ["uv", "run", str(CHECK_SCRIPT), feature],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(project_root),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        # subprocess 失败（如 uv 不在 PATH）-> 降级放行，在 stderr 打印警告
        sys.stderr.write(
            "[rpiv-loop] check_acceptance.py 调用失败\n"
            f"  错误: {exc}\n"
            "  降级放行（请手工执行 check_acceptance.py 验证后再提交）。\n"
        )
        return 0

    if result.returncode == 0:
        return 0

    sys.stderr.write(
        "[rpiv-loop] DoD gate 未通过 — delivery-report 阶段禁止写入\n"
        f"  文件: {posix}\n"
        f"  特性: {feature}\n"
        f"  check_acceptance.py 退出码: {result.returncode}\n"
        "  失败详情:\n"
    )
    stdout_content = result.stdout.strip()
    if stdout_content:
        for line in stdout_content.splitlines():
            sys.stderr.write(f"    {line}\n")
    stderr_content = result.stderr.strip()
    if stderr_content:
        for line in stderr_content.splitlines():
            sys.stderr.write(f"    {line}\n")
    sys.stderr.write(
        "  请先在 validate 阶段补齐 evidence/status，再重新生成交付报告。\n"
        "  规范: delivery-report SKILL '第 0 步 AC gate 硬校验'。\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
