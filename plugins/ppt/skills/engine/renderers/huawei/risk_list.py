"""华为主题 renderer: risk-list (S4 Phase 1 从 renderers_huawei.py 拆出)。

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


@register_renderer("risk-list")
def render_risk_list(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int) -> None:
    """风险列表：2 列卡片，每卡 number/title/desc/mitigation + severity 标签。"""
    ctx = RendererContext.build(slide, spec, theme, safe, total_slides)

    cfg = _layout(theme, "risk_list")
    cols_max = cfg.get("columns_max", 2)
    sev_bar_px = cfg.get("severity_bar_width_px", 4)

    font = ctx.font
    area_left, area_top, area_w, area_h = ctx.area_left, ctx.area_top, ctx.area_w, ctx.area_h

    risks = _extra(spec, "risks", default=None) or []
    if not risks:
        for p in get_points(spec):
            risks.append({
                "title": p.heading or "",
                "desc": p.body or "",
                "severity": "MED",
            })
    # L-6 fix: cols 自适应 ceil(sqrt(n)), card 尺寸按 (canvas - margins - gutters) / (cols, rows) 撑满
    # 旧实现 cols 固定 2 + card_h 上限 2.4", n=4/5 时画布大量空白.
    n = max(len(risks), 1)
    import math as _math
    cols = max(1, min(cols_max, int(_math.ceil(_math.sqrt(n)))))
    # 横向布局优先 (PPT 16:9): 列数 ≥ 行数, 让 cols ≥ rows
    rows = (n + cols - 1) // cols
    if rows > cols and cols < cols_max:
        # 升 cols 到不超过 cols_max, 让 rows 减
        cols = min(cols_max, rows)
        rows = (n + cols - 1) // cols
    gap = 0.25
    card_w = (area_w - gap * (cols - 1)) / cols
    card_h = (area_h - gap * (rows - 1)) / rows  # 不再设 2.4 上限, 数量少时单卡变大填满

    primary = _color(theme, "primary", "#C7000B")
    accent = _color(theme, "accent", "#D97706")
    ok_c = _color(theme, "ok", "#1E7B3A")
    paper_2 = _color(theme, "paper_2", "#F4F4F4")
    paper = _color(theme, "paper", "#FFFFFF")
    ink = _color(theme, "ink", "#1F1F1F")
    ink_soft = _color(theme, "ink_soft", "#4B4B4B")
    ink_mute = _color(theme, "ink_mute", "#9A9A9A")
    body_pt = _px_pt(_type_px(theme, "body", 24))
    small_pt = _px_pt(_type_px(theme, "small", 20))
    h4_pt = _px_pt(_type_px(theme, "h4", 28))
    sev_bar_in = _px_in(sev_bar_px)

    sev_color = {
        "HIGH": primary,
        "H": primary,
        "MED": accent,
        "M": accent,
        "LOW": ok_c,
        "L": ok_c,
    }

    for i, risk in enumerate(risks):
        if isinstance(risk, str):
            risk = {"title": risk, "desc": "", "severity": "MED"}
        r = i // cols
        c = i % cols
        x = area_left + c * (card_w + gap)
        y = area_top + r * (card_h + gap)
        if y + card_h > area_top + area_h:
            break

        # 背景
        add_rounded_rect(slide, x, y, card_w, card_h, paper_2, corner_radius=0.08)
        # 左侧 severity bar
        sev = str(_dget(risk, "severity", default="MED")).upper()
        bar_color = sev_color.get(sev, accent)
        _add_rect(slide, x, y, sev_bar_in, card_h, bar_color)

        # 序号
        num_text = f"R{i + 1:02d}"
        add_textbox(
            slide, x + sev_bar_in + 0.2, y + 0.1, 1.0, small_pt / 72 * 1.4 + 0.1,
            num_text, font, small_pt,
            bar_color, bold=True,
        )
        # severity 标签
        add_textbox(
            slide, x + card_w - 1.2, y + 0.1, 1.0, small_pt / 72 * 1.4 + 0.1,
            sev, font, small_pt,
            bar_color, alignment=PP_ALIGN.RIGHT, bold=True,
        )
        # 标题
        title_text = str(_dget(risk, "title", default=""))
        add_textbox(
            slide, x + sev_bar_in + 0.2, y + 0.5,
            card_w - sev_bar_in - 0.3, h4_pt / 72 * 1.4 + 0.15,
            title_text, font, h4_pt,
            ink, bold=True,
        )
        # 描述
        desc_text = str(_dget(risk, "desc", "description", default=""))
        if desc_text:
            add_textbox(
                slide, x + sev_bar_in + 0.2,
                y + 0.5 + h4_pt / 72 * 1.4 + 0.15,
                card_w - sev_bar_in - 0.3, body_pt / 72 * 1.8 + 0.2,
                desc_text, font, small_pt,
                ink_soft,
            )
        # 缓解措施
        mit_text = str(_dget(risk, "mitigation", default=""))
        if mit_text:
            add_textbox(
                slide, x + sev_bar_in + 0.2,
                y + card_h - small_pt / 72 * 1.5 - 0.3,
                card_w - sev_bar_in - 0.3, small_pt / 72 * 1.5 + 0.1,
                f"→ {mit_text}", font, small_pt,
                bar_color, bold=True,
            )


