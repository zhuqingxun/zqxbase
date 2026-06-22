"""LayoutEngine 纯几何单测 (S4 god-module 阶段3 第一阶段)。

两组断言:
1. **几何恒等**: split_columns / split_rows / split_grid 的输出坐标与各 renderer 原硬编码
   公式 (area_w/n, (area_h-gap*(n-1))/n, divmod 网格...) 逐项恒等 (pytest.approx 容浮点)。
2. **layouts.yaml 契约** (AC-002 验收源): 8 个迁移 renderer 的 section 必须有 `layout` 子节
   且 `type` ∈ {columns, rows, grid}。迁移全部完成前此组会 fail (预期)。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.layout_engine import (
    Region,
    region_from_area,
    split_columns,
    split_grid,
    split_rows,
)

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LAYOUTS_YAML = PLUGIN_ROOT / "themes" / "huawei" / "layouts.yaml"


# ---------------------------------------------------------------------------
# split_columns
# ---------------------------------------------------------------------------
class TestSplitColumns:
    def test_equal_no_gap(self):
        r = Region(1.0, 2.0, 9.0, 5.0)
        cols = split_columns(r, 3, 0.0)
        assert len(cols) == 3
        col_w = 9.0 / 3
        for i, c in enumerate(cols):
            assert c.left == pytest.approx(1.0 + i * col_w)
            assert c.width == pytest.approx(col_w)
            assert c.top == pytest.approx(2.0)
            assert c.height == pytest.approx(5.0)

    def test_with_gap(self):
        r = Region(0.0, 0.0, 12.0, 4.0)
        gap = 0.25
        cols = split_columns(r, 4, gap)
        col_w = (12.0 - gap * 3) / 4
        for i, c in enumerate(cols):
            assert c.width == pytest.approx(col_w)
            assert c.left == pytest.approx(0.0 + i * (col_w + gap))

    def test_n_one(self):
        r = Region(1.0, 1.0, 8.0, 3.0)
        cols = split_columns(r, 1, 0.0)
        assert len(cols) == 1
        assert cols[0].left == pytest.approx(1.0)
        assert cols[0].width == pytest.approx(8.0)

    def test_n_zero_clamped_to_one(self):
        r = Region(0.0, 0.0, 6.0, 2.0)
        cols = split_columns(r, 0, 0.0)
        assert len(cols) == 1
        assert cols[0].width == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# split_rows
# ---------------------------------------------------------------------------
class TestSplitRows:
    def test_equal_no_cap(self):
        r = Region(1.0, 2.0, 9.0, 6.0)
        rows = split_rows(r, 3, 0.0)
        row_h = 6.0 / 3
        for i, row in enumerate(rows):
            assert row.top == pytest.approx(2.0 + i * row_h)
            assert row.height == pytest.approx(row_h)
            assert row.left == pytest.approx(1.0)
            assert row.width == pytest.approx(9.0)

    def test_with_gap(self):
        r = Region(0.0, 0.0, 5.0, 10.0)
        gap = 0.2
        rows = split_rows(r, 4, gap)
        row_h = (10.0 - gap * 3) / 4
        for i, row in enumerate(rows):
            assert row.height == pytest.approx(row_h)
            assert row.top == pytest.approx(0.0 + i * (row_h + gap))

    def test_cap_applies_when_equal_share_exceeds_cap(self):
        # height/5 = 1.0 > cap 0.82 → 取 0.82 (toc 多条目场景)
        r = Region(0.0, 2.0, 9.0, 5.0)
        rows = split_rows(r, 5, 0.0, row_height_cap=0.82)
        for i, row in enumerate(rows):
            assert row.height == pytest.approx(0.82)
            assert row.top == pytest.approx(2.0 + i * 0.82)

    def test_cap_inactive_when_equal_share_below_cap(self):
        # height/2 = 1.0 但... 设 height 使 share < cap: height=1.0,n=2 → share 0.5 < 0.82 取 0.5
        r = Region(0.0, 0.0, 9.0, 1.0)
        rows = split_rows(r, 2, 0.0, row_height_cap=0.82)
        for row in rows:
            assert row.height == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# split_grid
# ---------------------------------------------------------------------------
class TestSplitGrid:
    def test_2x2_no_gap(self):
        r = Region(1.0, 2.0, 8.0, 6.0)
        cells = split_grid(r, 2, 2, 0.0)
        assert len(cells) == 4
        cell_w, cell_h = 8.0 / 2, 6.0 / 2
        # row-major: idx0=左上, 1=右上, 2=左下, 3=右下
        assert (cells[0].left, cells[0].top) == pytest.approx((1.0, 2.0))
        assert (cells[1].left, cells[1].top) == pytest.approx((1.0 + cell_w, 2.0))
        assert (cells[2].left, cells[2].top) == pytest.approx((1.0, 2.0 + cell_h))
        assert (cells[3].left, cells[3].top) == pytest.approx((1.0 + cell_w, 2.0 + cell_h))
        for c in cells:
            assert c.width == pytest.approx(cell_w)
            assert c.height == pytest.approx(cell_h)

    def test_3x2_with_gap(self):
        r = Region(0.0, 0.0, 12.0, 7.0)
        gap = 0.25
        cells = split_grid(r, 2, 3, gap)
        assert len(cells) == 6
        cell_w = (12.0 - gap * 2) / 3
        cell_h = (7.0 - gap * 1) / 2
        # idx4 → r=1,c=1
        assert cells[4].left == pytest.approx(0.0 + 1 * (cell_w + gap))
        assert cells[4].top == pytest.approx(0.0 + 1 * (cell_h + gap))

    def test_single_cell(self):
        r = Region(2.0, 3.0, 4.0, 5.0)
        cells = split_grid(r, 1, 1, 0.0)
        assert len(cells) == 1
        assert cells[0] == Region(2.0, 3.0, 4.0, 5.0)


# ---------------------------------------------------------------------------
# 与原 renderer 硬编码公式逐项恒等
# ---------------------------------------------------------------------------
class TestIdentityWithLegacyFormulas:
    """复刻三个 renderer 的原始切分公式, 断言 split_* 输出与其逐项相等。"""

    def test_swot_grid_identity(self):
        # swot.py:48-49,73-75: cell_w=area_w/2, cell_h=area_h/2, x=area_left+col*cell_w
        area_left, area_top, area_w, area_h = 1.0, 2.4, 11.34, 4.6
        cell_w = area_w / 2
        cell_h = area_h / 2
        cells = split_grid(Region(area_left, area_top, area_w, area_h), 2, 2, 0.0)
        for i in range(4):
            row, col = divmod(i, 2)
            assert cells[i].left == pytest.approx(area_left + col * cell_w)
            assert cells[i].top == pytest.approx(area_top + row * cell_h)

    def test_timeline_columns_identity(self):
        # timeline_huawei.py:57,78: col_w=area_w/n, x=area_left+i*col_w
        area_left, area_top, area_w, area_h = 0.96, 2.32, 11.41, 4.42
        n = 4
        col_w = area_w / n
        cols = split_columns(Region(area_left, area_top, area_w, area_h), n, 0.0)
        for i in range(n):
            assert cols[i].left == pytest.approx(area_left + i * col_w)
            assert cols[i].width == pytest.approx(col_w)

    def test_architecture_rows_identity(self):
        # architecture_layered.py:71,90: layer_h=(area_h-gap*(n-1))/n, y=area_top+li*(layer_h+gap)
        area_left, area_top, area_w, area_h = 0.96, 2.32, 11.41, 4.42
        n_layers = 3
        gap_in = 14 / 96.0  # _px_in(layer_gap_px=14)
        layer_h = (area_h - gap_in * (n_layers - 1)) / n_layers
        rows = split_rows(Region(area_left, area_top, area_w, area_h), n_layers, gap_in)
        for li in range(n_layers):
            assert rows[li].top == pytest.approx(area_top + li * (layer_h + gap_in))
            assert rows[li].height == pytest.approx(layer_h)

    def test_matrix_grid_identity(self):
        # matrix_2x2.py:61-62,154-159: cell_w=(grid_w-gap)/2, 4 象限固定坐标
        grid_left, grid_top, grid_w, grid_h = 2.42, 2.32, 9.95, 2.96
        gap_in = 20 / 96.0  # _px_in(grid_gap_px=20)
        cell_w = (grid_w - gap_in) / 2
        cell_h = (grid_h - gap_in) / 2
        cells = split_grid(Region(grid_left, grid_top, grid_w, grid_h), 2, 2, gap_in)
        expected = [
            (grid_left, grid_top),
            (grid_left + cell_w + gap_in, grid_top),
            (grid_left, grid_top + cell_h + gap_in),
            (grid_left + cell_w + gap_in, grid_top + cell_h + gap_in),
        ]
        for i, (ex, ey) in enumerate(expected):
            assert cells[i].left == pytest.approx(ex)
            assert cells[i].top == pytest.approx(ey)


# ---------------------------------------------------------------------------
# region_from_area
# ---------------------------------------------------------------------------
def test_region_from_area_duck_typed():
    class _Ctx:
        area_left = 0.96
        area_top = 2.32
        area_w = 11.41
        area_h = 4.42

    r = region_from_area(_Ctx())
    assert r == Region(0.96, 2.32, 11.41, 4.42)


# ---------------------------------------------------------------------------
# layouts.yaml 契约 (AC-002): 8 个迁移 renderer 必须有 layout 子节
# ---------------------------------------------------------------------------
_MIGRATED_RENDERERS = [
    "swot",
    "timeline_huawei",
    "toc",
    "process_flow_huawei",
    "personas",
    "architecture_layered",
    "matrix_2x2",
    "cards_6",
]
_VALID_LAYOUT_TYPES = {"columns", "rows", "grid"}


def _load_layouts() -> dict:
    return yaml.safe_load(LAYOUTS_YAML.read_text(encoding="utf-8"))


@pytest.mark.parametrize("section", _MIGRATED_RENDERERS)
def test_migrated_renderer_has_layout_subnode(section: str):
    data = _load_layouts()
    assert section in data, f"layouts.yaml 缺 section: {section}"
    layout = data[section].get("layout")
    assert layout is not None, f"{section} 缺 layout 子节"
    assert layout.get("type") in _VALID_LAYOUT_TYPES, (
        f"{section}.layout.type={layout.get('type')!r} 不在 {_VALID_LAYOUT_TYPES}"
    )
