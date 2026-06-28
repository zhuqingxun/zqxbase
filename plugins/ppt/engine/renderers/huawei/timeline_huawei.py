"""华为主题 renderer: timeline-huawei (S4 Phase 1 从 renderers_huawei.py 拆出)。

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
    _truncate_for_single_line, _add_textbox_no_wrap, safe_h,
    _px_pt, _px_in, _resolve_gap_in, _tokens, _layouts, _color, _lerp_hex, _is_dark, _type_px, _layout,
    _extra, _extra_list_merge, _estimate_text_height_in, _dget, _add_rect,
    _canvas_dims_in, _canvas_padding_in, _slide_dims_in, _font_family, TREND_COLOR_TOKEN,
)
from engine.layout_engine import split_columns, region_from_area


@register_renderer("timeline-huawei")
def render_timeline_huawei(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int) -> None:
    """华为时间轴：顶部年份大字 48px + 阶段连接线 + 阶段标题 22px + 描述 16px。"""
    ctx = RendererContext.build(slide, spec, theme, safe, total_slides)

    cfg = _layout(theme, "timeline_huawei")
    year_px = cfg.get("year_size_px", 48)
    title_px = cfg.get("title_size_px", 22)
    desc_px = cfg.get("desc_size_px", 16)

    font = ctx.font
    area_left, area_top, area_w, area_h = ctx.area_left, ctx.area_top, ctx.area_w, ctx.area_h

    phases = _extra(spec, "phases", default=None) or _extra(spec, "timeline", default=None) or []
    if not phases:
        for p in get_points(spec):
            phases.append({
                "year": p.heading or "",
                "title": p.metric_label or "",
                "desc": p.body or "",
            })
    n = max(len(phases), 1)
    col_w = area_w / n

    # S4 阶段3: 横向等宽分栏交给 LayoutEngine (无 layout: 子节走原 col_w 路径)。
    # gap=0 时 cols[i].left == area_left+i*col_w、cols[i].width == col_w 逐 EMU 恒等。
    layout_spec = cfg.get("layout")
    cols = (
        split_columns(region_from_area(ctx), n, _resolve_gap_in(layout_spec, cfg))
        if layout_spec is not None else None
    )

    year_pt = _px_pt(year_px)
    title_pt = _px_pt(title_px)
    desc_pt = _px_pt(desc_px)

    primary = _color(theme, "primary", "#C7000B")
    ink = _color(theme, "ink", "#1F1F1F")
    ink_soft = _color(theme, "ink_soft", "#4B4B4B")
    rule_c = _color(theme, "rule", "#D9D9D9")

    # 横贯连接线
    line_y = area_top + year_pt / 72 * 1.3 + 0.4
    _add_rect(
        slide, area_left, line_y, area_w, 0.03,
        rule_c,
    )

    for i, phase in enumerate(phases):
        if isinstance(phase, str):
            phase = {"year": "", "title": phase, "desc": ""}
        if cols is not None:
            x, cw = cols[i].left, cols[i].width
        else:
            x, cw = area_left + i * col_w, col_w
        cy = area_top

        year_text = str(_dget(phase, "year", default=""))
        add_textbox(
            slide, x, cy, cw, year_pt / 72 * 1.3 + 0.2,
            year_text, font, year_pt,
            primary, bold=True,
        )

        # 节点圆点
        node_d = 0.25
        node_shape = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(x + cw / 2 - node_d / 2),
            Inches(line_y - node_d / 2 + 0.015),
            Inches(node_d), Inches(node_d),
        )
        node_shape.fill.solid()
        node_shape.fill.fore_color.rgb = hex_to_rgb(primary)
        node_shape.line.fill.background()

        body_top = line_y + 0.3
        # schemas: TimelinePhase.label/items[]; legacy: title/desc/description
        title_text = _dget(phase, "title", "label", default="")
        add_textbox(
            slide, x + 0.1, body_top, cw - 0.2, title_pt / 72 * 1.4 + 0.15,
            title_text, font, title_pt,
            ink, bold=True,
        )
        # desc 优先 string; 若 schemas 给的是 items list, 折叠成 "• item1\n• item2"
        desc_text = _dget(phase, "desc", "description", default="")
        if not desc_text:
            items_list = _dget(phase, "items", default=None)
            if isinstance(items_list, (list, tuple)) and items_list:
                desc_text = "\n".join(f"• {it}" for it in items_list)
        if desc_text:
            add_textbox(
                slide, x + 0.1,
                body_top + title_pt / 72 * 1.4 + 0.1,
                cw - 0.2,
                safe_h(area_top + area_h - body_top - title_pt / 72 * 1.4 - 0.1),
                desc_text, font, desc_pt,
                ink_soft,
            )


