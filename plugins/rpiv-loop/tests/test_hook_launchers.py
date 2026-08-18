from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOK_CONFIG = PLUGIN_ROOT / "hooks" / "hooks.json"
PYTHON_COMMAND_PREFIX = 'uv run --no-project python -B -c "'


def _commands(value: Any) -> list[str]:
    if isinstance(value, dict):
        found = [value["command"]] if isinstance(value.get("command"), str) else []
        for item in value.values():
            found.extend(_commands(item))
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            found.extend(_commands(item))
        return found
    return []


def test_all_hook_launchers_fail_open_without_plugin_root() -> None:
    payload = json.loads(HOOK_CONFIG.read_text(encoding="utf-8"))
    commands = _commands(payload)
    environment = os.environ.copy()
    environment.pop("RPIV_LOOP_ROOT", None)
    environment.pop("CLAUDE_PLUGIN_ROOT", None)

    assert len(commands) == 4
    for command in commands:
        assert command.startswith(PYTHON_COMMAND_PREFIX)
        assert command.endswith('"')
        code = command[len(PYTHON_COMMAND_PREFIX) : -1]
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            input="{}",
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )

        assert result.returncode == 0
        assert result.stderr == ""
