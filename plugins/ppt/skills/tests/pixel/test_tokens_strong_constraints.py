# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=7.0", "pyyaml>=6.0"]
# ///
"""T15 配套测试：强约束值（色值 / 字号 / 布局）对账。

直接验证 themes/huawei/tokens.yaml 和 layouts.yaml 与 PRD §11 期望值一致。
不依赖 Dev 渲染器实现，只需 Dev T2（tokens/layouts 写入）完成即可跑。

对应规格：SPEC-PX-C-*（色值）/ SPEC-PX-T-*（字号）/ SPEC-PX-L-*（布局）。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

THEME_DIR = Path(__file__).resolve().parents[2] / "themes" / "huawei"
TOKENS_PATH = THEME_DIR / "tokens.yaml"
LAYOUTS_PATH = THEME_DIR / "layouts.yaml"

pytestmark = pytest.mark.skipif(
    not (TOKENS_PATH.exists() and LAYOUTS_PATH.exists()),
    reason="tokens.yaml / layouts.yaml 尚未就绪（Dev T2 前）",
)


@pytest.fixture(scope="module")
def tokens() -> dict:
    return yaml.safe_load(TOKENS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def layouts() -> dict:
    return yaml.safe_load(LAYOUTS_PATH.read_text(encoding="utf-8"))


# ============================================================
# Colors（SPEC-PX-C-1..6 + 扩展）
# ============================================================

EXPECTED_COLORS: dict[str, str] = {
    "primary": "#C7000B",
    "primary_dark": "#8A0008",
    "primary_soft": "#FDECEE",
    "ink": "#1F1F1F",
    "ink_soft": "#4B4B4B",
    "ink_mute": "#9A9A9A",
    "ink_dark": "#2A2A2A",
    "rule": "#D9D9D9",
    "rule_soft": "#ECECEC",
    "paper": "#FFFFFF",
    "paper_2": "#F4F4F4",
    "paper_3": "#EAEAEA",
    "accent": "#D97706",
}


@pytest.mark.parametrize("key,expected", EXPECTED_COLORS.items(), ids=list(EXPECTED_COLORS))
def test_token_color_exact(tokens, key, expected):
    """色值零容忍：PRD §7.5.1 6 色 + Plan §tokens.yaml 全部 13 色必须精确匹配大写 hex。"""
    actual = tokens.get("colors", {}).get(key)
    assert actual == expected, f"colors.{key}: expected {expected}, got {actual!r}"


# ============================================================
# Type scale（SPEC-PX-T-1..5 + 扩展）
# ============================================================

EXPECTED_TYPE_SCALE: dict[str, int] = {
    "cover": 108,
    "section": 84,
    "title": 54,
    "subtitle": 36,
    "h4": 28,
    "body": 24,
    "small": 20,
    "micro": 16,
    "nano": 14,
}


@pytest.mark.parametrize("key,expected", EXPECTED_TYPE_SCALE.items(), ids=list(EXPECTED_TYPE_SCALE))
def test_type_scale_px(tokens, key, expected):
    """字号档位：必须与 PRD §6.3 一致，tolerance=0。"""
    actual = tokens.get("type_scale_px", {}).get(key)
    assert actual == expected, f"type_scale_px.{key}: expected {expected}, got {actual!r}"


# ============================================================
# Canvas padding（SPEC-PX-L-5）
# ============================================================

EXPECTED_CANVAS: dict[str, int] = {
    "width_px": 1920,
    "height_px": 1080,
    "padding_top_px": 88,
    "padding_left_px": 96,
    "padding_right_px": 96,
    "padding_bottom_px": 76,
}


@pytest.mark.parametrize("key,expected", EXPECTED_CANVAS.items(), ids=list(EXPECTED_CANVAS))
def test_canvas_padding(layouts, key, expected):
    """画布 + padding 四边：±0 px 精确匹配。"""
    actual = layouts.get("canvas", {}).get(key)
    assert actual == expected, f"canvas.{key}: expected {expected}, got {actual!r}"


# ============================================================
# 版式专属强约束（SPEC-PX-L-1..4 + Plan layouts.yaml）
# ============================================================

EXPECTED_LAYOUT_STRONG: dict[tuple[str, str], int | str] = {
    ("cover_left_bar", "bar_width_px"): 16,
    ("cover_left_bar", "title_size_px"): 108,
    ("section_divider_dark", "big_number_size_px"): 360,
    ("section_divider_dark", "big_number_weight"): 200,
    ("section_divider_dark", "title_size_px"): 88,
    ("section_divider_dark", "background_token"): "ink_dark",
    ("matrix_2x2", "border_width_px"): 2,
    ("matrix_2x2", "border_token"): "ink",
    ("architecture_layered", "header_column_px"): 260,
    ("architecture_layered", "cell_columns"): 6,
    ("kpi_stats", "value_size_px"): 108,  # §O6 权威值（HTML 实测，原 96 为 pre-O6 旧值）
}


@pytest.mark.parametrize(
    "group,key,expected",
    [(g, k, v) for (g, k), v in EXPECTED_LAYOUT_STRONG.items()],
    ids=[f"{g}.{k}" for (g, k) in EXPECTED_LAYOUT_STRONG],
)
def test_layout_strong_constraint(layouts, group, key, expected):
    """PRD §11 强约束项：封面红条 16px / 章节数字 360px / 矩阵 border 2px / arch 层头 260px / KPI 数字 96px 等。"""
    actual = layouts.get(group, {}).get(key)
    assert actual == expected, f"layouts.{group}.{key}: expected {expected}, got {actual!r}"


# ============================================================
# Fonts（Plan T2 的 fonts 字段）
# ============================================================

def test_fonts_sans_stack(tokens):
    """字体栈：Inter + Noto Sans SC + Microsoft YaHei（顺序敏感）。"""
    sans = tokens.get("fonts", {}).get("sans")
    assert sans == ["Inter", "Noto Sans SC", "Microsoft YaHei"], f"got {sans!r}"


def test_fonts_mono_stack(tokens):
    """mono 字体栈。"""
    mono = tokens.get("fonts", {}).get("mono")
    assert mono == ["JetBrains Mono"], f"got {mono!r}"


# ============================================================
# 结构完整性（非强约束但必须存在）
# ============================================================

def test_tokens_top_level_keys(tokens):
    """tokens.yaml 顶层必须包含 colors / fonts / type_scale_px 三组。"""
    assert set(tokens.keys()) >= {"colors", "fonts", "type_scale_px"}


def test_layouts_top_level_keys(layouts):
    """layouts.yaml 顶层必须包含 canvas + 17+ 个 visual_type 专属分组。"""
    assert "canvas" in layouts
    # 每个 P0 P1 P2 版式都必须有布局参数（snake_case）
    required_groups = {
        "cover_left_bar", "toc", "section_divider_dark", "kpi_stats",
        "matrix_2x2", "architecture_layered", "timeline_huawei", "process_flow_huawei",
        "swot", "roadmap", "pyramid", "heatmap_matrix", "thankyou",
        "cards_6", "rings", "personas",
    }
    missing = required_groups - set(layouts.keys())
    assert not missing, f"layouts.yaml 缺少分组: {sorted(missing)}"
