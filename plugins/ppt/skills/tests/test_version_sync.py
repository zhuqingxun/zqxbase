"""测试 plugin 版本三层同步 (AC-027 + Leader 派工 #6 + Plan §10).

按 ~/.claude/CLAUDE.md "Plugin/Skill 修改必须 bump 版本号" 强制规则:
- plugin.json (.claude-plugin/plugin.json)
- skills/create/SKILL.md (frontmatter)
- skills/refine/SKILL.md (frontmatter)
- skills/theme/SKILL.md (frontmatter)
四个版本字段必须严格相等。本 PRD 实施后预期值: 3.1.0 (minor bump).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
SKILLS_DIR = PLUGIN_ROOT / "skills"

# Plan §10 规定的 minor bump 目标版本; 后续 PRD 推进时本常量同步刷新
EXPECTED_VERSION = "3.1.0"

# SKILL.md frontmatter version 字段提取正则
_VERSION_RE = re.compile(
    r"""^version:\s*["']?([^"'\s]+)["']?\s*$""",
    re.MULTILINE,
)


def _read_plugin_json_version() -> str:
    """读 plugin.json 顶层 version 字段."""
    data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    version = data.get("version")
    assert isinstance(version, str), f"plugin.json version 字段非 str: {version!r}"
    return version


def _read_skill_md_version(skill_name: str) -> str | None:
    """读 skills/<name>/SKILL.md frontmatter version. 文件不存在返回 None."""
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_md.exists():
        return None
    text = skill_md.read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    assert match is not None, (
        f"skills/{skill_name}/SKILL.md 缺 frontmatter version 字段"
    )
    return match.group(1).strip()


# ============================================================
# AC-027: 三层 (实际 4 文件) 版本字符串严格一致
# ============================================================

class TestPluginVersionSync:
    """plugin.json + 3 个 SKILL.md 的 version 字段必须严格相等."""

    def test_plugin_json_exists(self):
        """plugin.json 必须存在."""
        assert PLUGIN_JSON.exists(), f"{PLUGIN_JSON} 不存在"

    def test_plugin_json_version_matches_expected(self):
        """plugin.json version == 3.1.0 (Plan §10 minor bump 目标)."""
        version = _read_plugin_json_version()
        assert version == EXPECTED_VERSION, (
            f"plugin.json version {version!r} != {EXPECTED_VERSION!r} "
            f"(Plan §10: 本 PRD 应 minor bump 到 3.1.0)"
        )

    @pytest.mark.parametrize("skill_name", ["create", "refine", "theme"])
    def test_skill_md_version_matches_expected(self, skill_name: str):
        """每个 SKILL.md frontmatter version == 3.1.0."""
        version = _read_skill_md_version(skill_name)
        if version is None:
            # theme/SKILL.md 在某些 layout 下可能不存在; create/refine 必须存在
            if skill_name in ("create", "refine"):
                pytest.fail(f"skills/{skill_name}/SKILL.md 缺失")
            pytest.skip(f"skills/{skill_name}/SKILL.md 不存在 (可选 skill)")
        assert version == EXPECTED_VERSION, (
            f"skills/{skill_name}/SKILL.md version {version!r} != "
            f"{EXPECTED_VERSION!r}"
        )

    def test_all_versions_identical(self):
        """4 个版本字段必须严格 byte-equal (即使不等于 EXPECTED_VERSION 也应一致).

        这条比 EXPECTED_VERSION 检查更宽松——只要 4 处一致即可,
        允许未来 PRD bump 到 3.2.0 / 4.0.0 等版本时本测试自然跟随.
        """
        plugin_v = _read_plugin_json_version()
        versions: dict[str, str] = {"plugin.json": plugin_v}
        for skill_name in ("create", "refine", "theme"):
            v = _read_skill_md_version(skill_name)
            if v is not None:
                versions[f"skills/{skill_name}/SKILL.md"] = v

        # 至少应有 plugin.json + create + refine 三处
        assert len(versions) >= 3, (
            f"版本源不足 3 处: {list(versions.keys())}"
        )

        unique_values = set(versions.values())
        assert len(unique_values) == 1, (
            "版本三层不一致 (~/.claude/CLAUDE.md 强制规则违反):\n"
            + "\n".join(f"  - {k}: {v}" for k, v in versions.items())
        )
