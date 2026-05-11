"""测试 SlideDesign 默认色去蓝 (P4 + AC-019).

依赖 Dev P4: schemas/slide_plan.py SlideDesign 默认色字段改为 None
- title_color: str | None = None    # 历史: "#1A1A2E"
- body_color: str | None = None     # 历史: "#4A4A68"
- accent_color: str | None = None   # 历史: "#2563EB"
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SLIDE_PLAN_PY = PLUGIN_ROOT / "schemas" / "slide_plan.py"
RENDER_PY = PLUGIN_ROOT / "engine" / "render.py"

# 4 个历史蓝色码,本 PRD 完成后这些值不应再出现于 schemas/slide_plan.py 与 render.py
LEGACY_BLUE_HEX = (
    "#2563EB",    # 历史 accent_color (品牌蓝)
    "#F0F4FF",    # 历史 default fill
    "#1A1A2E",    # 历史 title_color
    "#4A4A68",    # 历史 body_color
)


# ============================================================
# AC-019 静态检查: schemas/slide_plan.py 不含历史蓝色码
# ============================================================

class TestSlidePlanNoHardcodedBlue:
    """AC-019: schemas/slide_plan.py 默认色字段去蓝."""

    @pytest.fixture(scope="class")
    def slide_plan_text(self) -> str:
        if not SLIDE_PLAN_PY.exists():
            pytest.skip(f"{SLIDE_PLAN_PY} 不存在")
        return SLIDE_PLAN_PY.read_text(encoding="utf-8")

    @pytest.mark.parametrize("blue_hex", LEGACY_BLUE_HEX)
    def test_no_legacy_blue_in_slide_plan_py(self, slide_plan_text: str, blue_hex: str):
        """schemas/slide_plan.py 不应含历史蓝色码 (大小写不敏感)."""
        # 大小写不敏感比较 (yaml 经常混用)
        pattern = re.compile(re.escape(blue_hex), re.IGNORECASE)
        matches = pattern.findall(slide_plan_text)
        assert not matches, (
            f"schemas/slide_plan.py 仍含历史蓝色码 {blue_hex} ({len(matches)} 处)"
            f" — Dev P4 应改为 None 默认值"
        )

    def test_slide_design_color_fields_default_none_or_token(self, slide_plan_text: str):
        """SlideDesign 的 title_color / body_color / accent_color 默认值应为 None.

        (允许过渡期: 默认引用 theme token 字符串如 'theme.colors.ink' 也接受)
        """
        # grep 三个字段定义行
        for field in ("title_color", "body_color", "accent_color"):
            field_pattern = re.compile(
                rf"^\s*{field}\s*:\s*(.+?)\s*=\s*(.+?)$",
                re.MULTILINE,
            )
            match = field_pattern.search(slide_plan_text)
            if match:
                annotation = match.group(1).strip()
                default = match.group(2).strip()
                # 默认值: None / "" / 注释指向 theme token / 含 None
                assert (
                    default == "None"
                    or "None" in annotation
                    or "theme" in default.lower()
                ), (
                    f"SlideDesign.{field} 默认 {default} 不符合 P4 规范 "
                    "(应为 None 或主题 token 引用)"
                )


# ============================================================
# AC-020 静态检查: render.py 6 处装饰色不含历史蓝
# ============================================================

class TestRenderPyNoHardcodedBlue:
    """AC-020: engine/render.py 装饰色去蓝."""

    @pytest.fixture(scope="class")
    def render_text(self) -> str:
        if not RENDER_PY.exists():
            pytest.skip(f"{RENDER_PY} 不存在")
        return RENDER_PY.read_text(encoding="utf-8")

    @pytest.mark.parametrize("blue_hex", LEGACY_BLUE_HEX)
    def test_no_legacy_blue_in_render_py(self, render_text: str, blue_hex: str):
        """engine/render.py 不应含历史蓝色码."""
        pattern = re.compile(re.escape(blue_hex), re.IGNORECASE)
        matches = pattern.findall(render_text)
        # 允许注释中提及 (如说明"历史蓝") - 排除注释行
        non_comment_lines = [
            line for line in render_text.split("\n")
            if pattern.search(line) and not line.strip().startswith("#")
        ]
        assert not non_comment_lines, (
            f"engine/render.py 非注释行仍含 {blue_hex}:\n"
            + "\n".join(non_comment_lines[:5])
        )


# ============================================================
# AC-019 行为检查: SlideDesign 实例化默认色为 None
# ============================================================

class TestSlideDesignBehavior:
    """SlideDesign 实例化无 override 时,color 字段默认 None."""

    def test_slide_design_default_colors_are_none(self):
        """SlideDesign() 默认 title_color / body_color / accent_color is None."""
        try:
            from schemas.slide_plan import SlideDesign
        except ImportError:
            pytest.skip("schemas.slide_plan 不可导入")

        design = SlideDesign()
        # P4 实施后这 3 个字段默认应为 None
        assert design.title_color is None, (
            f"P4 后 title_color 默认应 None, 实际 {design.title_color}"
        )
        assert design.body_color is None, (
            f"P4 后 body_color 默认应 None, 实际 {design.body_color}"
        )
        assert design.accent_color is None, (
            f"P4 后 accent_color 默认应 None, 实际 {design.accent_color}"
        )

    def test_slide_design_explicit_colors_still_work(self):
        """显式传 color 参数仍然生效 (向后兼容)."""
        try:
            from schemas.slide_plan import SlideDesign
        except ImportError:
            pytest.skip("schemas.slide_plan 不可导入")

        design = SlideDesign(
            title_color="#FF0000",
            body_color="#00FF00",
            accent_color="#0000FF",
        )
        assert design.title_color == "#FF0000"
        assert design.body_color == "#00FF00"
        assert design.accent_color == "#0000FF"
