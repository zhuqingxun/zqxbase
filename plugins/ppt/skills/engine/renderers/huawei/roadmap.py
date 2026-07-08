"""华为主题 renderer: roadmap (S4 Phase 1 从 renderers_huawei.py 拆出)。

helper 单一来源在 engine.renderer_kit; 本模块仅含单个 @register_renderer。
"""
from __future__ import annotations

from typing import Any

from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from lxml import etree

from lib.font_fallback import resolve_font_for_pptx
from lib.margins import SafeArea
from schemas.slide_plan import SlideSpec, StructuredPoint

from engine.renderer_kit import (
    register_renderer, _RENDERERS, RendererContext,
    hex_to_rgb, add_textbox, add_textbox_rich, add_rounded_rect, set_slide_background,
    render_title_zone, render_footer, get_content_zone, get_points, get_point_bodies,
    _render_cards, _resolve_accent, _resolve_title_color, _resolve_body_color, _ve,
    compute_card_height, estimate_content_height, normalize_point,
    render_card_header, render_card_number_badge, _get_card_accent,
    _truncate_for_single_line, _add_textbox_no_wrap,
    _px_pt, _px_in, _tokens, _layouts, _color, _lerp_hex, _is_dark, _type_px, _layout,
    _extra, _extra_list_merge, _estimate_text_height_in, _dget, _add_rect,
    _canvas_dims_in, _canvas_padding_in, _slide_dims_in, _font_family, TREND_COLOR_TOKEN,
)


@register_renderer("roadmap")
def render_roadmap(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int) -> None:
    """Roadmap 泳道图：左侧 lane 列 + 右侧多阶段横向条，按 emphasis 映射填充色。"""
    ctx = RendererContext.build(slide, spec, theme, safe, total_slides)

    cfg = _layout(theme, "roadmap")
    lane_col_px = cfg.get("lane_column_px", 180)

    font = ctx.font
    area_left, area_top, area_w, area_h = ctx.area_left, ctx.area_top, ctx.area_w, ctx.area_h

    lane_w = _px_in(lane_col_px)
    body_pt = _px_pt(_type_px(theme, "body", 24))
    small_pt = _px_pt(_type_px(theme, "small", 20))

    phases = _extra(spec, "phases", default=None) or ["Q1", "Q2", "Q3", "Q4"]
    n_phases = max(len(phases), 1)
    right_x = area_left + lane_w + 0.15
    right_w = area_w - lane_w - 0.15
    phase_col_w = right_w / n_phases

    primary = _color(theme, "primary", "#C7000B")
    accent = _color(theme, "accent", "#D97706")
    paper_2 = _color(theme, "paper_2", "#F4F4F4")
    ink = _color(theme, "ink", "#1F1F1F")
    ink_soft = _color(theme, "ink_soft", "#4B4B4B")

    # Phase 表头: title 主显 + summary 副显 (双层)
    title_h = 0.28
    summary_h = 0.32
    header_h = title_h + summary_h
    summary_pt = max(_px_pt(_type_px(theme, "small", 20)) - 4, 10)
    for pi, ph in enumerate(phases):
        if isinstance(ph, str):
            title_text = ph
            summary_text = ""
        else:
            title_text = str(_dget(ph, "title", default="") or "")
            summary_text = str(_dget(ph, "summary", default="") or "")
        add_textbox(
            slide, right_x + pi * phase_col_w, area_top,
            phase_col_w, title_h,
            title_text, font, small_pt,
            ink_soft, alignment=PP_ALIGN.CENTER, bold=True,
        )
        if summary_text:
            add_textbox(
                slide, right_x + pi * phase_col_w, area_top + title_h,
                phase_col_w, summary_h,
                summary_text, font, summary_pt,
                ink_soft, alignment=PP_ALIGN.CENTER, bold=False,
            )

    emphasis_fill = {
        "primary": primary,
        "accent": accent,
        "bar": primary,
        "bar2": accent,
        "default": paper_2,
    }
    emph_on = ("primary", "accent", "bar", "bar2")  # 高亮填充 → 白字

    # path X (schema RoadmapContent): rows[].cells[] 网格 — cell[ci] 对齐 phase 列 ci。
    # 历史 bug: renderer 只认 lanes/bars (start/span 横条模型), schema 的 rows/cells 静默丢失,
    # 渲染只剩 phase 标题行 + 70% 空白。现优先消费 rows, 缺失时退回 legacy lanes/bars。
    rows = _extra(spec, "rows", default=None) or []
    if rows:
        n_lanes = max(len(rows), 1)
        lane_h = (area_h - header_h - 0.15) / n_lanes
        for li, row in enumerate(rows):
            if isinstance(row, str):
                row = {"label": row, "cells": []}
            ly = area_top + header_h + 0.15 + li * lane_h
            # 泳道标签 (schema: label; legacy alias: name) — 垂直居中
            lbx = add_textbox(
                slide, area_left, ly, lane_w, lane_h,
                str(_dget(row, "label", "name", default="")), font, body_pt,
                ink, bold=True,
            )
            lbx.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            cells = _dget(row, "cells", "bars", default=[]) or []
            for ci, cell in enumerate(cells):
                if ci >= n_phases:
                    break  # cell 超出 phase 列数则忽略 (网格只有 n_phases 列)
                if isinstance(cell, str):
                    cell = {"title": cell}
                emphasis = str(_dget(cell, "emphasis", default="") or "")
                fill = emphasis_fill.get(emphasis, paper_2)
                cx = right_x + ci * phase_col_w + 0.06
                cw = max(phase_col_w - 0.12, 0.3)
                cyy = ly + 0.06
                chh = max(lane_h - 0.12, 0.3)
                add_rounded_rect(slide, cx, cyy, cw, chh, fill, corner_radius=0.08)
                cell_title = str(_dget(cell, "title", "label", default=""))
                cell_desc = str(_dget(cell, "desc", "description", default=""))
                t_color = "#FFFFFF" if emphasis in emph_on else ink
                d_color = "#FFFFFF" if emphasis in emph_on else ink_soft
                ty = cyy + 0.1
                if cell_title:
                    th = small_pt / 72 * 1.4 + 0.08
                    add_textbox(
                        slide, cx + 0.14, ty, cw - 0.28, th,
                        cell_title, font, small_pt, t_color, bold=True,
                    )
                    ty += th
                if cell_desc:
                    add_textbox(
                        slide, cx + 0.14, ty, cw - 0.28, max(chh - (ty - cyy) - 0.08, 0.2),
                        cell_desc, font, max(small_pt - 4, 10), d_color,
                    )
        return

    # T13 (ARCH-002 阶段3): path Y legacy lanes/bars 横条分支已删除。
    # SlideContent extra='forbid' 后 content.lanes/bars 不可达 (typed RoadmapContent 走 rows/cells
    # path X 上方分支, 且 rows 为必填 min_length=1 → path X 永远命中, 此处不可达)。
    # 随分支一并删除 T14 加的 start/span 非整数 guard (path Y 专用, path X cells 无 start/span 字段)。
    # 兜底: 万一 rows 为空 (理论上 schema 拦截), 仅渲染 phase 表头, 不再 fallback 横条模型。


