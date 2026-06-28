# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""detect_codex.py: codex CLI 可用性检测 (ppt codex 引擎的路由门禁).

四项检测全部通过才算可用:
1. CLI 存在 (shutil.which)
2. 版本可解析 (`codex --version` 输出匹配 `codex-cli X.Y.Z`)
3. 已认证 (CODEX_HOME 或 ~/.codex 下 auth.json 存在; 只查存在性, 不读内容)
4. presentations 插件已启用 (config.toml 的 plugins 表中 presentations@* 条目 enabled=true)

输出契约 (PRD §10):
- 全部通过: exit 0 + stdout JSON {"available": true, "codex_version": "X.Y.Z", "presentations": true}
- 任一失败: exit 1 + stdout JSON {"available": false, "reason": "<具体缺什么>"}

Usage:
    uv run --script scripts/detect_codex.py [--codex-cmd codex]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

EXIT_OK = 0
EXIT_FAIL = 1

_VERSION_RE = re.compile(r"codex-cli (\d+\.\d+\.\d+)")


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _fail(reason: str) -> int:
    _emit({"available": False, "reason": reason})
    return EXIT_FAIL


def detect(codex_cmd: str) -> int:
    """执行四项检测, 返回 exit code 并打印 JSON 结果."""
    # 1. CLI 存在 (Windows 下 which 自动解析 .cmd shim)
    codex_path = shutil.which(codex_cmd)
    if not codex_path:
        return _fail(f'codex CLI 未找到: which("{codex_cmd}") 无结果')

    # 2. 版本
    try:
        proc = subprocess.run(
            [codex_path, "--version"],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return _fail(f"codex --version 超时 (15s): {codex_path}")
    except OSError as exc:
        return _fail(f"codex --version 执行失败: {exc}")
    match = _VERSION_RE.search(proc.stdout or "")
    if proc.returncode != 0 or not match:
        return _fail(
            f"codex --version 输出无法解析 (returncode={proc.returncode}): "
            f"{(proc.stdout or '').strip()[:200]}"
        )
    codex_version = match.group(1)

    # 3. 认证: 只查 auth.json 存在性, 禁止读内容 (token 不得进日志)
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    auth_path = codex_home / "auth.json"
    if not auth_path.exists():
        return _fail(f"auth.json 不存在: {auth_path} (codex 未登录?)")

    # 4. presentations 插件: 遍历 plugins 表找 presentations@ 前缀条目 (防 runtime 名漂移)
    config_path = codex_home / "config.toml"
    presentations_enabled = False
    if config_path.exists():
        try:
            with open(config_path, "rb") as fh:
                config = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            return _fail(f"config.toml 解析失败: {config_path}: {exc}")
        plugins = config.get("plugins", {})
        for key, entry in plugins.items():
            if key.startswith("presentations@") and isinstance(entry, dict):
                if entry.get("enabled") is True:
                    presentations_enabled = True
                    break
    if not presentations_enabled:
        return _fail(
            f"presentations 插件未启用: {config_path} 的 plugins 表中"
            "无 enabled=true 的 presentations@* 条目"
        )

    _emit({
        "available": True,
        "codex_version": codex_version,
        "presentations": True,
    })
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description="codex CLI 可用性检测")
    parser.add_argument(
        "--codex-cmd", default="codex",
        help="codex 命令名或路径 (默认 codex)",
    )
    args = parser.parse_args()
    return detect(args.codex_cmd)


if __name__ == "__main__":
    sys.exit(main())
