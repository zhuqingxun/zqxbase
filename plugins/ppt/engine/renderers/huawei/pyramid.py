"""华为主题 renderer: pyramid (S4 Phase 1 从 renderers_huawei.py 拆出)。

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


@register_renderer("pyramid")
def render_pyramid(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int) -> None:
    """金字塔：N 层 TRAPEZOID 自顶向下递增宽度。"""
    ctx = RendererContext.build(slide, spec, theme, safe, total_slides)

    cfg = _layout(theme, "pyramid")
    levels_default = cfg.get("levels_default", 4)
    top_ratio = float(cfg.get("top_width_ratio", 0.35))

    font = ctx.font
    area_left, area_top, area_w, area_h = ctx.area_left, ctx.area_top, ctx.area_w, ctx.area_h

    # L-7 fix Bug B 配套: 用 _extra_list_merge 同时取 path X (variant) 和 path Y (content) 的 levels,
    # 避免 LLM 双写时字段不一致导致数据丢失 (如 variant.levels 只有 name, content.levels 有 title+desc).
    levels = _extra_list_merge(spec, "levels")
    if not levels:
        for p in get_points(spec):
            levels.append({"title": p.heading or "", "desc": p.body or ""})
    n = len(levels) or levels_default

    # L-7 主体: 优先用独立 descriptions[] (schemas 字段, 比 levels.desc 更精细), 以 layer center 为 anchor 对齐.
    descriptions = _extra_list_merge(spec, "descriptions")

    # 金字塔整体：左侧 55% 宽，右侧留给描述
    pyr_w = area_w * 0.55
    pyr_cx = area_left + pyr_w / 2
    layer_h = area_h / n

    # 2026-05-31 taste A 红色渐变阶梯: 顶浓红(primary) → 底极浅红 线性插值,
    # 替代旧 顶 primary_dark + 二 primary + 下 paper_2 的"红红灰灰灰"断裂配色 (顶层近黑被用户评低)
    grad_top = _color(theme, cfg.get("gradient_top_token", "primary"), "#C7000B")
    grad_bottom = cfg.get("gradient_bottom_hex", "#FBE9EA")
    paper = _color(theme, "paper", "#FFFFFF")
    ink = _color(theme, "ink", "#1F1F1F")
    ink_soft = _color(theme, "ink_soft", "#4B4B4B")
    body_pt = _px_pt(_type_px(theme, "body", 24))
    small_pt = _px_pt(_type_px(theme, "small", 20))
    h4_pt = _px_pt(_type_px(theme, "h4", 28))

    # 每层梯形：自顶向下宽度线性递增 top_ratio → 1.0
    for i in range(n):
        level = levels[i] if i < len(levels) else {}
        if isinstance(level, str):
            level = {"title": level, "desc": ""}
        frac_top = top_ratio + (1.0 - top_ratio) * (i / n)
        frac_bot = top_ratio + (1.0 - top_ratio) * ((i + 1) / n)
        top_w = pyr_w * frac_top
        bot_w = pyr_w * frac_bot
        # 用 TRAPEZOID 近似：取底宽为 bot_w，adj 控制上底比例
        y = area_top + i * layer_h
        shape = slide.shapes.add_shape(
            MSO_SHAPE.TRAPEZOID,
            Inches(pyr_cx - bot_w / 2), Inches(y),
            Inches(bot_w), Inches(layer_h - 0.03),
        )
        shape.fill.solid()
        # 顶浓红 → 底极浅红连贯渐变 (taste A); n=1 时取顶色
        layer_t = i / (n - 1) if n > 1 else 0.0
        layer_hex = _lerp_hex(grad_top, grad_bottom, layer_t)
        shape.fill.fore_color.rgb = hex_to_rgb(layer_hex)
        shape.line.fill.background()

        # TRAPEZOID 的 adj 设置（控制上底比例）
        try:
            sp = shape._element
            prstGeom = sp.find(qn("a:prstGeom"))
            if prstGeom is not None:
                avLst = prstGeom.find(qn("a:avLst"))
                if avLst is None:
                    avLst = etree.SubElement(prstGeom, qn("a:avLst"))
                # adj = (bot_w - top_w) / 2 / bot_w × 100000（留边百分比）
                adj_val = int(max(0.0, (bot_w - top_w) / 2 / max(bot_w, 0.01)) * 100000)
                gd = etree.SubElement(avLst, qn("a:gd"))
                gd.set("name", "adj")
                gd.set("fmla", f"val {adj_val}")
        except Exception:
            pass

        # 层内文字 (schemas: name; legacy: title)
        title_text = _dget(level, "title", "name", default="")
        text_color = paper if _is_dark(layer_hex) else ink
        add_textbox(
            slide, pyr_cx - bot_w / 2, y + (layer_h - 0.03) / 2 - 0.2,
            bot_w, 0.4,
            title_text, font, body_pt,
            text_color, alignment=PP_ALIGN.CENTER, bold=True,
        )

        # 右侧描述: 优先用独立 descriptions[i], 以 layer center 为 anchor 链式定位
        # 兜底: legacy 用 level.desc/description/tag
        rx = area_left + pyr_w + 0.3
        rw = area_w - pyr_w - 0.3
        layer_center_y = y + (layer_h - 0.03) / 2
        if i < len(descriptions):
            d = descriptions[i]
            num = _dget(d, "number", default="")
            heading = _dget(d, "heading", default="")
            body = _dget(d, "body", default="")
            head_pt = small_pt
            head_h = head_pt / 72 * 1.4 + 0.1
            body_pt_local = small_pt - 1
            body_h = max(
                body_pt_local / 72 * 1.5 + 0.2,
                _estimate_text_height_in(body, rw, body_pt_local, line_spacing=1.4, padding_in=0.1),
            ) if body else 0.0
            block_h = head_h + body_h
            block_top = layer_center_y - block_h / 2
            head_text = f"{num}  {heading}".strip() if num else heading
            if head_text:
                add_textbox(
                    slide, rx, block_top, rw, head_h,
                    head_text, font, head_pt,
                    ink, bold=True,
                )
            if body:
                add_textbox(
                    slide, rx, block_top + head_h, rw, body_h,
                    body, font, body_pt_local,
                    ink_soft,
                )
        else:
            desc_text = _dget(level, "desc", "description", "tag", default="")
            if desc_text:
                add_textbox(
                    slide, rx, y + 0.1, rw, layer_h - 0.1,
                    f"• {desc_text}", font, small_pt,
                    ink_soft,
                )


