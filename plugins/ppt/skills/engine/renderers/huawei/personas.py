"""华为主题 renderer: personas (S4 Phase 1 从 renderers_huawei.py 拆出)。

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


@register_renderer("personas")
def render_personas(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int) -> None:
    """人物画像卡：2-4 列 role/name/attrs/quote。quote 左侧 3pt 红 accent bar。"""
    sw, sh = _slide_dims_in()
    set_slide_background(slide, _color(theme, "paper", "#FFFFFF"))
    render_title_zone(slide, spec, theme, safe)
    render_footer(slide, spec, theme, safe, total_slides)

    cfg = _layout(theme, "personas")
    cols_max = cfg.get("columns_max", 4)
    accent_bar_px = cfg.get("quote_accent_bar_px", 3)

    top_pad, right_pad, bottom_pad, left_pad = _canvas_padding_in(theme)
    font = _font_family(spec, theme)

    area_left = left_pad
    area_top = top_pad + 1.4
    area_w = sw - area_left - right_pad
    area_h = sh - area_top - bottom_pad - 0.5

    personas = _extra(spec, "personas", default=None) or []
    if not personas:
        for p in get_points(spec):
            personas.append({
                "role": p.heading or "",
                "name": p.metric_label or "",
                "attrs": [],
                "quote": p.body or "",
            })
    n = min(len(personas), cols_max) or 1
    gap = 0.25
    col_w = (area_w - gap * (n - 1)) / n

    primary = _color(theme, "primary", "#C7000B")
    paper_2 = _color(theme, "paper_2", "#F4F4F4")
    ink = _color(theme, "ink", "#1F1F1F")
    ink_soft = _color(theme, "ink_soft", "#4B4B4B")
    ink_mute = _color(theme, "ink_mute", "#9A9A9A")
    body_pt = _px_pt(_type_px(theme, "body", 24))
    small_pt = _px_pt(_type_px(theme, "small", 20))
    h4_pt = _px_pt(_type_px(theme, "h4", 28))
    accent_bar_in = _px_in(accent_bar_px)

    for i in range(n):
        item: Any = personas[i] if i < len(personas) else {}
        if isinstance(item, str):
            item = {"role": "", "name": "", "attrs": [], "quote": item}
        x = area_left + i * (col_w + gap)
        cy = area_top

        # role
        role_text = str(_dget(item, "role", default=""))
        if role_text:
            add_textbox(
                slide, x, cy, col_w, small_pt / 72 * 1.4 + 0.1,
                role_text, font, small_pt,
                primary, bold=True,
            )
            cy += small_pt / 72 * 1.4 + 0.05
        # name
        name_text = str(_dget(item, "name", default=""))
        if name_text:
            add_textbox(
                slide, x, cy, col_w, h4_pt / 72 * 1.4 + 0.1,
                name_text, font, h4_pt,
                ink, bold=True,
            )
            cy += h4_pt / 72 * 1.4 + 0.2

        # attrs（label/value 对）
        attrs = _dget(item, "attrs", default=[]) or []
        for attr in attrs[:6]:
            if isinstance(attr, dict):
                label = str(_dget(attr, "label", default=""))
                value = str(_dget(attr, "value", default=""))
                line = f"{label}  {value}"
            else:
                line = str(attr)
            add_textbox(
                slide, x, cy, col_w, small_pt / 72 * 1.5 + 0.1,
                line, font, small_pt,
                ink_soft,
            )
            cy += small_pt / 72 * 1.5 + 0.05

        # quote：左红条 + 灰底 rounded rect
        quote = str(_dget(item, "quote", default=""))
        if quote:
            cy += 0.1
            quote_h = min(area_top + area_h - cy - 0.1, 2.0)
            if quote_h > 0.4:
                # 背景
                add_rounded_rect(slide, x, cy, col_w, quote_h, paper_2, corner_radius=0.06)
                # 红条
                _add_rect(slide, x, cy, accent_bar_in, quote_h, primary)
                add_textbox(
                    slide, x + accent_bar_in + 0.15, cy + 0.15,
                    col_w - accent_bar_in - 0.3, quote_h - 0.3,
                    f"“{quote}”", font, small_pt,
                    ink_soft,
                )


