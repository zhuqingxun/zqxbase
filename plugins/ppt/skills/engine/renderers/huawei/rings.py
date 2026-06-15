"""华为主题 renderer: rings (S4 Phase 1 从 renderers_huawei.py 拆出)。

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
    register_renderer, _RENDERERS,
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


@register_renderer("rings")
def render_rings(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int) -> None:
    """同心环：左侧 3 层同心椭圆 + 右侧步骤列表。"""
    sw, sh = _slide_dims_in()
    set_slide_background(slide, _color(theme, "paper", "#FFFFFF"))
    render_title_zone(slide, spec, theme, safe)
    render_footer(slide, spec, theme, safe, total_slides)

    cfg = _layout(theme, "rings")
    ring_max = cfg.get("ring_count_max", 3)
    right_gap_px = cfg.get("right_list_gap_px", 28)

    top_pad, right_pad, bottom_pad, left_pad = _canvas_padding_in(theme)
    font = _font_family(spec, theme)

    area_left = left_pad
    area_top = top_pad + 1.4
    area_w = sw - area_left - right_pad
    area_h = sh - area_top - bottom_pad - 0.5

    rings = _extra(spec, "rings", default=None) or []
    steps = _extra(spec, "steps", default=None) or []
    if not rings:
        # 退化：用 points 前 ring_max 条
        for p in get_points(spec)[:ring_max]:
            rings.append({"label": p.heading or p.body})

    n = min(len(rings), ring_max) if rings else ring_max
    left_w = area_w * 0.45
    ring_cx = area_left + left_w / 2
    ring_cy = area_top + area_h / 2

    primary = _color(theme, "primary", "#C7000B")
    primary_dark = _color(theme, "primary_dark", "#8A0008")
    primary_soft = _color(theme, "primary_soft", "#FDECEE")
    paper = _color(theme, "paper", "#FFFFFF")
    ink = _color(theme, "ink", "#1F1F1F")
    ink_soft = _color(theme, "ink_soft", "#4B4B4B")

    # 最大直径
    max_d = min(left_w * 0.85, area_h * 0.85)
    step_d = max_d / n

    # 外→内绘制：外层浅 / 空心边框，内层实心
    for i in range(n):
        d = max_d - i * step_d
        x = ring_cx - d / 2
        y = ring_cy - d / 2
        shape = slide.shapes.add_shape(
            MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d),
        )
        if i == n - 1:
            shape.fill.solid()
            shape.fill.fore_color.rgb = hex_to_rgb(primary)
            shape.line.fill.background()
        else:
            shape.fill.background()
            shape.line.color.rgb = hex_to_rgb(primary_dark if i == 0 else primary)
            shape.line.width = Pt(2.5)

        # 环标签 (path X: Ring 是 pydantic 子模型, 不能 str(item) 否则渲染出 repr; 用 _dget 取 label)
        label = ""
        if i < len(rings):
            item = rings[i]
            if isinstance(item, str):
                label = item
            else:
                label = str(_dget(item, "label", default=""))
        if label:
            label_w = d * 0.9
            label_x = ring_cx - label_w / 2
            # 外两层顶部标注，内层中心
            if i == n - 1:
                label_y = ring_cy - 0.25
                color = paper
            else:
                label_y = y + 0.1
                color = ink
            add_textbox(
                slide, label_x, label_y, label_w, 0.5,
                label, font, _px_pt(_type_px(theme, "small", 20)),
                color, alignment=PP_ALIGN.CENTER, bold=True,
            )

    # 右侧步骤列表
    if not steps:
        for p in get_points(spec):
            steps.append({"title": p.heading or "", "desc": p.body or ""})
    right_x = area_left + left_w + 0.3
    right_w = area_w - left_w - 0.3
    gap_in = _px_in(right_gap_px)
    body_pt = _px_pt(_type_px(theme, "body", 24))
    small_pt = _px_pt(_type_px(theme, "small", 20))
    cy = area_top + 0.1
    for i, step in enumerate(steps):
        if isinstance(step, str):
            step = {"title": step, "desc": ""}
        # schema RingStep 用 heading/body; legacy 用 title/desc — 双别名兼容 (path X 下 heading/body 曾丢)
        title_text = str(_dget(step, "title", "heading", default=""))
        desc_text = str(_dget(step, "desc", "description", "body", default=""))

        num_text = f"{i + 1:02d}"
        add_textbox(
            slide, right_x, cy, 0.8, body_pt / 72 * 1.4 + 0.1,
            num_text, font, body_pt,
            primary, bold=True,
        )
        add_textbox(
            slide, right_x + 0.8, cy, right_w - 0.8, body_pt / 72 * 1.4 + 0.1,
            title_text, font, body_pt,
            ink, bold=True,
        )
        if desc_text:
            add_textbox(
                slide, right_x + 0.8,
                cy + body_pt / 72 * 1.4 + 0.05,
                right_w - 0.8,
                small_pt / 72 * 1.6 + 0.2,
                desc_text, font, small_pt,
                ink_soft,
            )
        cy += body_pt / 72 * 1.4 + small_pt / 72 * 1.6 + 0.25 + gap_in
        if cy > area_top + area_h - 0.3:
            break


