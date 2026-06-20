# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=7.0", "pyyaml>=6.0", "python-pptx>=1.0.0", "pydantic>=2.0", "lxml>=4.9", "Pillow>=10.0"]
# ///
"""renderer_kit 共享 helper 纯函数单测 (S4 收敛重构 T16).

renderer_kit.py 是 Phase 1 抽出的共享 helper 单一来源 (解 render.py ↔ renderers_huawei.py
循环依赖)。本文件覆盖其中**无副作用的纯函数**:
- 颜色: hex_to_rgb / _lerp_hex / _is_dark
- 数据归一: normalize_point / get_points / get_point_bodies
- 几何: compute_card_height (clamp) / safe_h (高度下限钳制)

不覆盖需要 slide/theme 渲染上下文的 helper (那些走 test_renderer_convergence.py 的 render->extract)。
所有期望值均以 renderer_kit 当前实现实测为准 (自验后写入)。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


# ============================================================
# 颜色 helper
# ============================================================

class TestHexToRgb:
    def test_basic_conversion(self):
        """'#RRGGBB' → RGBColor(r, g, b)。"""
        from pptx.dml.color import RGBColor

        from engine.renderer_kit import hex_to_rgb
        assert hex_to_rgb("#FF8000") == RGBColor(0xFF, 0x80, 0x00)

    def test_str_roundtrip(self):
        """RGBColor str 形式回到 6 位大写 hex (无 #)。"""
        from engine.renderer_kit import hex_to_rgb
        assert str(hex_to_rgb("#1A2B3C")) == "1A2B3C"

    def test_leading_hash_optional(self):
        """带不带 # 结果一致 (实现 lstrip('#'))。"""
        from engine.renderer_kit import hex_to_rgb
        assert hex_to_rgb("#FFFFFF") == hex_to_rgb("FFFFFF")

    def test_black_and_white_endpoints(self):
        from pptx.dml.color import RGBColor

        from engine.renderer_kit import hex_to_rgb
        assert hex_to_rgb("#000000") == RGBColor(0, 0, 0)
        assert hex_to_rgb("#FFFFFF") == RGBColor(255, 255, 255)


class TestLerpHex:
    def test_endpoints(self):
        """t=0 取 c1, t=1 取 c2 (返回大写 #RRGGBB)。"""
        from engine.renderer_kit import _lerp_hex
        assert _lerp_hex("#000000", "#FFFFFF", 0.0) == "#000000"
        assert _lerp_hex("#000000", "#FFFFFF", 1.0) == "#FFFFFF"

    def test_midpoint_rounds(self):
        """t=0.5 黑↔白 → #808080 (round(127.5)=128=0x80)。"""
        from engine.renderer_kit import _lerp_hex
        assert _lerp_hex("#000000", "#FFFFFF", 0.5) == "#808080"

    def test_returns_uppercase_hash_prefixed(self):
        from engine.renderer_kit import _lerp_hex
        out = _lerp_hex("#abcdef", "#123456", 0.3)
        assert out.startswith("#") and out == out.upper() and len(out) == 7


class TestIsDark:
    def test_white_is_light(self):
        from engine.renderer_kit import _is_dark
        assert _is_dark("#FFFFFF") is False

    def test_black_is_dark(self):
        from engine.renderer_kit import _is_dark
        assert _is_dark("#000000") is True

    def test_mid_gray_below_threshold(self):
        """#808080 感知亮度 128 < 默认阈值 140 → 判暗。"""
        from engine.renderer_kit import _is_dark
        assert _is_dark("#808080") is True

    def test_threshold_param(self):
        """阈值可调: 把阈值压到 100 后中灰不再判暗。"""
        from engine.renderer_kit import _is_dark
        assert _is_dark("#808080", threshold=100.0) is False


# ============================================================
# 数据归一 helper
# ============================================================

class TestNormalizePoint:
    def test_str_with_colon_splits_heading_body(self):
        """'Heading: body' → StructuredPoint(heading, body)，按首个 ': ' 分。"""
        from engine.renderer_kit import normalize_point
        p = normalize_point("Heading: body text")
        assert p.heading == "Heading"
        assert p.body == "body text"

    def test_plain_str_becomes_body_only(self):
        """无 ': ' 的纯字符串 → 只填 body, heading=None。"""
        from engine.renderer_kit import normalize_point
        p = normalize_point("plain text")
        assert p.heading is None
        assert p.body == "plain text"

    def test_dict_passthrough(self):
        from engine.renderer_kit import normalize_point
        p = normalize_point({"heading": "X", "body": "Y"})
        assert p.heading == "X" and p.body == "Y"

    def test_structured_point_identity(self):
        """已是 StructuredPoint 时原样返回。"""
        from engine.renderer_kit import normalize_point
        from schemas.slide_plan import StructuredPoint
        sp = StructuredPoint(heading="h", body="b")
        assert normalize_point(sp) is sp


class TestGetPoints:
    def _spec(self, key_points):
        from schemas.slide_plan import SlideSpec
        return SlideSpec.model_validate({
            "id": 1, "role": "content", "visual_type": "bullets",
            "content": {"title": "t", "key_points": key_points},
        })

    def test_empty_key_points_returns_empty_list(self):
        """content.key_points 为 None/空 → []。"""
        from engine.renderer_kit import get_points
        assert get_points(self._spec(None)) == []
        assert get_points(self._spec([])) == []

    def test_normalizes_each_point(self):
        from engine.renderer_kit import get_points
        pts = get_points(self._spec(["A: a body", "plain"]))
        assert len(pts) == 2
        assert pts[0].heading == "A" and pts[0].body == "a body"
        assert pts[1].heading is None and pts[1].body == "plain"

    def test_get_point_bodies(self):
        from engine.renderer_kit import get_point_bodies
        from schemas.slide_plan import StructuredPoint
        bodies = get_point_bodies([
            StructuredPoint(heading="h", body="b1"),
            StructuredPoint(body="b2"),
        ])
        assert bodies == ["b1", "b2"]


# ============================================================
# 几何 helper
# ============================================================

class TestSafeH:
    def test_negative_clamped_to_default_min(self):
        """负高 → 0.1 (防 Inches(负值) 异常 shape)。"""
        from engine.renderer_kit import safe_h
        assert safe_h(-1.0) == pytest.approx(0.1)

    def test_below_min_clamped(self):
        from engine.renderer_kit import safe_h
        assert safe_h(0.05) == pytest.approx(0.1)

    def test_above_min_passthrough(self):
        from engine.renderer_kit import safe_h
        assert safe_h(2.0) == pytest.approx(2.0)

    def test_custom_minimum(self):
        from engine.renderer_kit import safe_h
        assert safe_h(0.2, minimum=0.5) == pytest.approx(0.5)


class TestComputeCardHeight:
    def test_min_clamp_for_short_content(self):
        """短内容不低于 min_height。"""
        from engine.renderer_kit import compute_card_height
        h = compute_card_height(["short"], card_width=3.0, font_size_pt=14,
                                max_height=5.0, min_height=1.5)
        assert h == pytest.approx(1.5)

    def test_max_clamp_for_tall_content(self):
        """超长内容被 max_height 钳住。"""
        from engine.renderer_kit import compute_card_height
        long_text = "很长的卡片正文 " * 200
        h = compute_card_height([long_text], card_width=3.0, font_size_pt=14,
                                max_height=2.5, min_height=1.0)
        assert h == pytest.approx(2.5)

    def test_empty_points_uses_min(self):
        """无 point 时 default=min_height。"""
        from engine.renderer_kit import compute_card_height
        h = compute_card_height([], card_width=3.0, font_size_pt=14,
                                max_height=5.0, min_height=1.5)
        assert h == pytest.approx(1.5)
