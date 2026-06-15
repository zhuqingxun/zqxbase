"""测试 plugin 版本同步 (AC-027).

按 ~/.claude/CLAUDE.md "Plugin/Skill 修改必须 bump 版本号" 强制规则:
- plugin.json (.claude-plugin/plugin.json)
- skills/create/SKILL.md (frontmatter)
- skills/refine/SKILL.md (frontmatter)
- skills/taste/SKILL.md (frontmatter)
- skills/theme/SKILL.md (frontmatter, 若存在)

实际存在的 SKILL.md 必须与 plugin.json 严格 byte-equal.
v3.4.0 起加入 taste; theme/SKILL.md 在 v3.4.0 被砍掉, 仅当目录仍在时一并校验.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
SKILLS_DIR = PLUGIN_ROOT / "skills"

# 目标版本; 后续 PRD 推进时同步刷新
EXPECTED_VERSION = "3.6.3"

# 所有 plugin 内 SKILL.md 子目录 (theme 可能在 v3.4.0+ 被删, 设 optional)
_REQUIRED_SKILLS = ("create", "refine", "taste")
_OPTIONAL_SKILLS = ("theme",)

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


class TestPluginVersionSync:
    """plugin.json + 所有存在的 SKILL.md 的 version 字段必须严格相等."""

    def test_plugin_json_exists(self):
        assert PLUGIN_JSON.exists(), f"{PLUGIN_JSON} 不存在"

    def test_plugin_json_version_matches_expected(self):
        version = _read_plugin_json_version()
        assert version == EXPECTED_VERSION, (
            f"plugin.json version {version!r} != {EXPECTED_VERSION!r}"
        )

    @pytest.mark.parametrize("skill_name", _REQUIRED_SKILLS)
    def test_required_skill_md_version_matches_expected(self, skill_name: str):
        """每个必需 SKILL.md frontmatter version == EXPECTED_VERSION."""
        version = _read_skill_md_version(skill_name)
        assert version is not None, f"skills/{skill_name}/SKILL.md 缺失 (必需 skill)"
        assert version == EXPECTED_VERSION, (
            f"skills/{skill_name}/SKILL.md version {version!r} != {EXPECTED_VERSION!r}"
        )

    @pytest.mark.parametrize("skill_name", _OPTIONAL_SKILLS)
    def test_optional_skill_md_version_matches_expected(self, skill_name: str):
        """可选 SKILL.md 若存在则版本必须对齐, 不存在则 skip."""
        version = _read_skill_md_version(skill_name)
        if version is None:
            pytest.skip(f"skills/{skill_name}/SKILL.md 不存在 (可选, 可能已 v3.4.0 砍掉)")
        assert version == EXPECTED_VERSION, (
            f"skills/{skill_name}/SKILL.md version {version!r} != {EXPECTED_VERSION!r}"
        )

    def test_all_versions_identical(self):
        """所有实际存在的版本源必须严格 byte-equal."""
        plugin_v = _read_plugin_json_version()
        versions: dict[str, str] = {"plugin.json": plugin_v}
        for skill_name in (*_REQUIRED_SKILLS, *_OPTIONAL_SKILLS):
            v = _read_skill_md_version(skill_name)
            if v is not None:
                versions[f"skills/{skill_name}/SKILL.md"] = v

        # 至少 plugin.json + 3 个必需 skill = 4 处
        assert len(versions) >= 1 + len(_REQUIRED_SKILLS), (
            f"版本源不足: {list(versions.keys())}"
        )

        unique_values = set(versions.values())
        assert len(unique_values) == 1, (
            "版本不一致 (~/.claude/CLAUDE.md 强制规则违反):\n"
            + "\n".join(f"  - {k}: {v}" for k, v in versions.items())
        )
