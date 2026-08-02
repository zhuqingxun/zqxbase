from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PLUGIN_ROOT / "tools" / "ensure_project_dod.py"
TEMPLATE_PATH = PLUGIN_ROOT / "tools" / "dod_template.yaml"


def _copy_tool(tmp_path: Path, *, include_template: bool) -> Path:
    tool_dir = tmp_path / "tool"
    tool_dir.mkdir()
    script = tool_dir / SCRIPT_PATH.name
    script.write_bytes(SCRIPT_PATH.read_bytes())
    if include_template:
        (tool_dir / TEMPLATE_PATH.name).write_bytes(TEMPLATE_PATH.read_bytes())
    return script


def _run(script: Path, project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_creates_dod_from_template_on_first_run(tmp_path: Path) -> None:
    script = _copy_tool(tmp_path, include_template=True)
    project = tmp_path / "project"
    project.mkdir()

    result = _run(script, project)

    target = project / "rpiv" / "dod.yaml"
    assert result.returncode == 0
    assert target.read_bytes() == TEMPLATE_PATH.read_bytes()
    assert "已创建 rpiv/dod.yaml" in result.stdout


def test_idempotent_on_second_run(tmp_path: Path) -> None:
    script = _copy_tool(tmp_path, include_template=True)
    project = tmp_path / "project"
    project.mkdir()
    first = _run(script, project)
    target = project / "rpiv" / "dod.yaml"
    target.write_text("custom project DoD\n", encoding="utf-8")

    second = _run(script, project)

    assert first.returncode == 0
    assert second.returncode == 0
    assert target.read_text(encoding="utf-8") == "custom project DoD\n"
    assert "已存在 rpiv/dod.yaml，跳过" in second.stdout


def test_missing_template_fails_when_target_is_absent(tmp_path: Path) -> None:
    script = _copy_tool(tmp_path, include_template=False)
    project = tmp_path / "project"
    project.mkdir()

    result = _run(script, project)

    assert result.returncode == 1
    assert not (project / "rpiv" / "dod.yaml").exists()
    assert "[rpiv-loop] 模板文件缺失" in result.stderr


def test_existing_target_skips_when_template_is_missing(tmp_path: Path) -> None:
    script = _copy_tool(tmp_path, include_template=False)
    project = tmp_path / "project"
    target = project / "rpiv" / "dod.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("existing\n", encoding="utf-8")

    result = _run(script, project)

    assert result.returncode == 0
    assert target.read_text(encoding="utf-8") == "existing\n"
    assert "已存在 rpiv/dod.yaml，跳过" in result.stdout
