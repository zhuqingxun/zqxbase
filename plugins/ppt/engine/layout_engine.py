"""LayoutEngine: region-agnostic 等分切分纯几何解释器 (S4 god-module 阶段3 第一阶段)。

最底层模块——仅依赖标准库 dataclasses, **不 import renderer_kit** (避免循环依赖:
renderer_kit 反向 import 本模块给 _render_cards 用)。

职责: renderer 拿到内容区矩形 region 后, 调 split_columns / split_rows / split_grid
拿子 region 列表, 再在子 region 内绘制。全部坐标用 float (inch) 不提前转 Inches/Emu——
与原各 renderer 硬编码公式 (area_w/n, (area_h-gap*(n-1))/n, ...) 逐 EMU 恒等。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    """一个矩形区域 (inch 为单位)。镜像 renderer_kit.RendererContext 的 frozen dataclass 风格。"""

    left: float
    top: float
    width: float
    height: float


def split_columns(region: Region, n: int, gap_in: float = 0.0) -> list[Region]:
    """横向等宽分栏: region 切成 n 列, 列间留 gap_in。

    与各 renderer 的 `col_w=(area_w-gap*(n-1))/n` + `x=area_left+i*(col_w+gap)` 逐项恒等。
    """
    n = max(n, 1)
    col_w = (region.width - gap_in * (n - 1)) / n
    return [
        Region(region.left + i * (col_w + gap_in), region.top, col_w, region.height)
        for i in range(n)
    ]


def split_rows(
    region: Region,
    n: int,
    gap_in: float = 0.0,
    row_height_cap: float | None = None,
) -> list[Region]:
    """纵向等高分行: region 切成 n 行, 行间留 gap_in。

    `row_height_cap` 非 None 时行高封顶 (专为 toc 的 `row_h=min(0.82,(bottom-top)/n)`);
    默认 None 退化为纯等分。与 `(area_h-gap*(n-1))/n` + `y=area_top+i*(row_h+gap)` 恒等。
    """
    n = max(n, 1)
    base = (region.height - gap_in * (n - 1)) / n
    row_h = min(row_height_cap, base) if row_height_cap is not None else base
    return [
        Region(region.left, region.top + i * (row_h + gap_in), region.width, row_h)
        for i in range(n)
    ]


def split_grid(region: Region, rows: int, cols: int, gap_in: float = 0.0) -> list[Region]:
    """规整网格: region 切成 rows×cols 个 cell (row-major), cell 间留 gap_in。

    返回 rows*cols 个 Region; 第 idx 个为 `r,c = divmod(idx, cols)`。
    与 swot 的 `cell_w=area_w/2`+`divmod(i,2)`、matrix 的 4 象限固定坐标逐项恒等。
    """
    rows = max(rows, 1)
    cols = max(cols, 1)
    cell_w = (region.width - gap_in * (cols - 1)) / cols
    cell_h = (region.height - gap_in * (rows - 1)) / rows
    out: list[Region] = []
    for idx in range(rows * cols):
        r, c = divmod(idx, cols)
        out.append(
            Region(
                region.left + c * (cell_w + gap_in),
                region.top + r * (cell_h + gap_in),
                cell_w,
                cell_h,
            )
        )
    return out


def region_from_area(ctx) -> Region:
    """从 RendererContext 便捷构造内容区 Region。

    duck-typed (只读 ctx.area_*), 不 import RendererContext 以保持本模块为最底层、避免循环依赖。
    """
    return Region(ctx.area_left, ctx.area_top, ctx.area_w, ctx.area_h)
