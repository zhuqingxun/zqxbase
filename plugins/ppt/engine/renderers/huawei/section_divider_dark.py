"""华为主题 renderer: section-divider-dark (S4 Phase 1 从 renderers_huawei.py 拆出)。

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


@register_renderer("section-divider-dark")
def render_section_divider_dark(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int) -> None:
    """章节过渡页（极简浅底版, 2026-05-31 taste 选型 B）: 小章节标签 + 短红线 + 克制标题 + 描述 + 大留白。

    历史: 旧版为深炭黑满底 (#2A2A2A) + 360px 巨号 + 88px 标题, 同时违反 anchors 原则
    P1(浅色优先) 与 P3(标题≤正文3倍/装饰字不应巨大), 用户在 us-military-rotation 评 0 分 (AP1+AP3)。
    现重排为浅底极简: 装饰号缩进标签 (~16pt), 标题降到 ~40pt, 全部 token/尺寸 cfg 可调。
    注册名保留 "section-divider-dark" 不改, 避免破坏 schema VALID_VISUAL_TYPES 映射。
    """
    sw, sh = _slide_dims_in()
    cfg = _layout(theme, "section_divider_dark")
    set_slide_background(slide, _color(theme, cfg.get("background_token", "paper"), "#FFFFFF"))

    top_pad, right_pad, bottom_pad, left_pad = _canvas_padding_in(theme)
    font = _font_family(spec, theme)
    red = _color(theme, cfg.get("tag_color_token", "primary"), "#C7000B")
    ink = _color(theme, cfg.get("title_color_token", "ink"), "#1F1F1F")
    ink_soft = _color(theme, cfg.get("desc_color_token", "ink_soft"), "#4B4B4B")

    tag_pt = _px_pt(cfg.get("tag_size_px", 27))       # ~16pt
    title_pt = _px_pt(cfg.get("title_size_px", 66))   # ~40pt (旧 88px=52.8pt, 现降到 ~40pt 合 P3)
    desc_pt = _px_pt(cfg.get("description_size_px", 27))

    x = left_pad + 0.3
    body_w = sw - x - right_pad

    # 章节标签: "<eyebrow> · <number>" — 装饰号缩进标签, 不再巨大
    number = _extra(spec, "number", "big_number") or str(spec.id).zfill(2)
    eyebrow = _extra(spec, "eyebrow", default=None) or spec.chapter or ""
    tag_text = f"{eyebrow} · {number}" if eyebrow else str(number)
    y = 1.55
    tag_h = tag_pt / 72 * 1.5 + 0.05
    add_textbox(slide, x, y, body_w, tag_h, tag_text, font, tag_pt, red, bold=True)

    # 标签下短红线
    rule_y = y + tag_h
    _add_rect(slide, x + 0.03, rule_y, 1.4, 0.05, red)

    # 标题 (克制, ~40pt)
    title_text_str = spec.content.title or ""
    title_y = rule_y + 0.32
    title_h = max(
        title_pt / 72 * 1.3 + 0.2,
        _estimate_text_height_in(title_text_str, body_w, title_pt, line_spacing=1.12, padding_in=0.15),
    )
    add_textbox(slide, x, title_y, body_w, title_h, title_text_str, font, title_pt, ink, bold=True)

    # 描述 (限宽 78% 留白) — 从 variant 取 (历史只读 content, path X 下 description 在 variant 里被丢)
    desc = _extra(spec, "description", "subtitle", default=None) or spec.content.description or spec.content.subtitle
    if desc:
        desc_y = title_y + title_h + 0.45
        desc_w = body_w * 0.78
        desc_h = _estimate_text_height_in(desc, desc_w, desc_pt, line_spacing=1.5, padding_in=0.2)
        max_h = sh - bottom_pad - desc_y - 0.2
        desc_h = min(desc_h, max(max_h, 0.5))
        add_textbox(slide, x, desc_y, desc_w, desc_h, desc, font, desc_pt, ink_soft)

    render_footer(slide, spec, theme, safe, total_slides)


