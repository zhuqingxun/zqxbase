"""华为主题 renderer: process-flow-huawei (S4 Phase 1 从 renderers_huawei.py 拆出)。

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
    _px_pt, _px_in, _resolve_gap_in, _tokens, _layouts, _color, _lerp_hex, _is_dark, _type_px, _layout,
    _extra, _extra_list_merge, _estimate_text_height_in, _dget, _add_rect,
    _canvas_dims_in, _canvas_padding_in, _slide_dims_in, _font_family, TREND_COLOR_TOKEN,
)
from engine.layout_engine import split_columns, region_from_area


@register_renderer("process-flow-huawei")
def render_process_flow_huawei(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int) -> None:
    """华为流程：N 个圆角 rect + 箭头连接器（步骤标题 24px / 描述 16px / 编号 14px）。"""
    ctx = RendererContext.build(slide, spec, theme, safe, total_slides)

    cfg = _layout(theme, "process_flow_huawei")
    arrow_gap_px = cfg.get("arrow_gap_px", 40)
    title_px = cfg.get("step_title_size_px", 24)
    desc_px = cfg.get("step_desc_size_px", 16)
    number_px = cfg.get("step_number_size_px", 14)

    font = ctx.font
    area_left, area_top, area_w, area_h = ctx.area_left, ctx.area_top, ctx.area_w, ctx.area_h

    steps = _extra(spec, "steps", default=None) or _extra(spec, "process", default=None) or []
    if not steps:
        for p in get_points(spec):
            steps.append({"title": p.heading or "", "desc": p.body or ""})
    n = max(len(steps), 1)

    arrow_gap_in = _px_in(arrow_gap_px)
    step_w = (area_w - arrow_gap_in * (n - 1)) / n

    # S4 阶段3: 带 gap 的横向分栏交给 LayoutEngine (无 layout: 子节走原 step_w 路径)。
    # gap_in:from_px:arrow_gap_px → _px_in(arrow_gap_px)==arrow_gap_in, 故 cols[i].left/width 与
    # 原 area_left+i*(step_w+arrow_gap_in) / step_w 逐 EMU 恒等。step_h content-driven clamp 留 renderer。
    layout_spec = cfg.get("layout")
    cols = (
        split_columns(region_from_area(ctx), n, _resolve_gap_in(layout_spec, cfg))
        if layout_spec is not None else None
    )

    title_pt = _px_pt(title_px)
    desc_pt = _px_pt(desc_px)
    number_pt = _px_pt(number_px)

    # step_h 按内容估算 (编号+标题固定 + 最大 desc 行高), 避免卡片过高、下半留空
    _hdr_zone = 0.5 + title_pt / 72 * 1.4 + 0.15
    _dmax = 0.0
    for _s in steps:
        _dt = "" if isinstance(_s, str) else str(_dget(_s, "desc", "description", default=""))
        if _dt:
            _dmax = max(_dmax, _estimate_text_height_in(_dt, step_w - 0.4, desc_pt, line_spacing=1.4, padding_in=0.1))
    step_h = max(1.3, min(2.6, _hdr_zone + _dmax + 0.25))
    step_top = area_top + (area_h - step_h) / 2

    primary = _color(theme, "primary", "#C7000B")
    primary_soft = _color(theme, "primary_soft", "#FDECEE")
    ink = _color(theme, "ink", "#1F1F1F")
    ink_soft = _color(theme, "ink_soft", "#4B4B4B")
    ink_mute = _color(theme, "ink_mute", "#9A9A9A")

    for i, step in enumerate(steps):
        if isinstance(step, str):
            step = {"title": step, "desc": ""}
        if cols is not None:
            x, cw = cols[i].left, cols[i].width
        else:
            x, cw = area_left + i * (step_w + arrow_gap_in), step_w

        # 圆角卡片（浅红底）
        add_rounded_rect(slide, x, step_top, cw, step_h, primary_soft, corner_radius=0.1)

        number_text = f"{i + 1:02d}"
        add_textbox(
            slide, x + 0.2, step_top + 0.15, cw - 0.4,
            number_pt / 72 * 1.5 + 0.1,
            number_text, font, number_pt,
            primary, bold=True,
        )
        # schemas: ProcessStep.label/desc; legacy: title
        title_text = _dget(step, "title", "label", default="")
        add_textbox(
            slide, x + 0.2, step_top + 0.5, cw - 0.4,
            title_pt / 72 * 1.4 + 0.15,
            title_text, font, title_pt,
            ink, bold=True,
        )
        desc_text = _dget(step, "desc", "description", default="")
        if desc_text:
            add_textbox(
                slide, x + 0.2,
                step_top + 0.5 + title_pt / 72 * 1.4 + 0.15,
                cw - 0.4,
                step_h - 0.7 - title_pt / 72 * 1.4,
                desc_text, font, desc_pt,
                ink_soft,
            )

        # 箭头（非末步）
        if i < n - 1:
            ax = x + cw + arrow_gap_in * 0.1
            ay = step_top + step_h / 2 - 0.15
            arr = slide.shapes.add_shape(
                MSO_SHAPE.RIGHT_ARROW,
                Inches(ax), Inches(ay),
                Inches(arrow_gap_in * 0.8), Inches(0.3),
            )
            arr.fill.solid()
            arr.fill.fore_color.rgb = hex_to_rgb(primary)
            arr.line.fill.background()


# ===========================================================================
# P1 五版式
# ===========================================================================

