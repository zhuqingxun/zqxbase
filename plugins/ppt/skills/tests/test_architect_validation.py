# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=7.0", "pyyaml>=6.0"]
# ///
"""validate_architecture 校准回归 (issue-ppt-validate-architecture-overstrict).

校准前: 真实满意产物 (us-military-rotation) 跑 research-report preset 报 8 个 issue
(5 个 chapter title 过短 + 3 个 required role 未覆盖) — 与真实华为风格脱节的 false-positive.

校准后:
- 真实满意产物 → 0 issue
- 结构章节 (封面/目录/致谢) 标题不再被 action_title 长度检查误伤
- 真实 9 字主题型内容章节标题不被误伤
- 退化 architecture (无章节 / 单字内容标题) 仍被拦截
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from engine.architect import load_preset, validate_architecture  # noqa: E402

FIXTURE_ARCH = (
    PLUGIN_ROOT / "tests" / "fixtures" / "us-military-rotation"
    / "recorded" / "architect-output.yaml"
)
_fixture_skip = pytest.mark.skipif(
    not FIXTURE_ARCH.exists(), reason=f"us-military fixture 缺失: {FIXTURE_ARCH}"
)


def _load_fixture_arch() -> dict:
    return yaml.safe_load(FIXTURE_ARCH.read_text(encoding="utf-8"))


@_fixture_skip
def test_real_satisfying_architecture_zero_issues():
    """验收核心: 真实满意产物跑 research-report preset → 0 issue (校准前 8 issue)。"""
    arch = _load_fixture_arch()
    preset = load_preset("research-report")
    issues = validate_architecture(arch, preset)
    assert issues == [], f"真实满意产物不应有 issue, 实际 {len(issues)} 条: {issues}"


@_fixture_skip
def test_structural_chapters_exempt_from_title_length():
    """封面/目录/致谢 结构章节标题 (2 字) 不触发 action_title 长度 issue。"""
    arch = _load_fixture_arch()
    preset = load_preset("research-report")
    titles = [c.get("title") for c in arch["chapters"]]
    assert "封面" in titles and "致谢" in titles, "前提: fixture 含结构章节"
    issues = validate_architecture(arch, preset)
    assert not any(("封面" in i) or ("目录" in i) or ("致谢" in i) for i in issues), (
        f"结构章节标题不应被拦截, 实际: {issues}"
    )


def test_no_chapters_still_flagged():
    """退化: architecture 无内容章节 → 内容型 required role 报 unmet (拦截保留)。"""
    preset = load_preset("research-report")
    arch = {"thesis": "x", "total_slides": 10, "chapters": []}
    issues = validate_architecture(arch, preset)
    assert any("role=" in i for i in issues), f"无章节应报 role 未覆盖, 实际: {issues}"


def test_single_char_content_title_flagged():
    """退化: 单字内容章节标题 → 过短 issue (拦截保留)。"""
    preset = load_preset("research-report")
    arch = {
        "thesis": "x", "total_slides": 10,
        "chapters": [
            {"title": "封面", "slide_briefs": [{"slide_id": 1}]},
            {"title": "短", "slide_briefs": [{"slide_id": 2}]},  # 单字内容章节
            {"title": "致谢", "slide_briefs": [{"slide_id": 3}]},
        ],
    }
    issues = validate_architecture(arch, preset)
    assert any("过短" in i for i in issues), f"单字内容标题应被拦截, 实际: {issues}"


def test_real_content_chapter_titles_pass():
    """真实 9 字主题型内容章节标题 (三层痛点与本质定位) 不被误伤。"""
    preset = load_preset("research-report")
    arch = {
        "thesis": "x", "total_slides": 10,
        "chapters": [
            {"title": "封面", "slide_briefs": [{"slide_id": 1}]},
            {"title": "三层痛点与本质定位", "slide_briefs": [{"slide_id": 2}]},  # 9 字
            {"title": "五大洞察与落地路径", "slide_briefs": [{"slide_id": 3}]},  # 9 字
        ],
    }
    issues = validate_architecture(arch, preset)
    assert not any("过短" in i for i in issues), f"9 字主题标题不应被误伤, 实际: {issues}"
