"""华为主题 renderer: architecture-layered (S4 Phase 1 从 renderers_huawei.py 拆出)。

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


@register_renderer("architecture-layered")
def render_architecture_layered(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int) -> None:
    """分层架构图：每层一行，左侧 header 列 + 右侧 N 个 cell；支持 highlight cell 红底白字。"""
    sw, sh = _slide_dims_in()
    set_slide_background(slide, _color(theme, "paper", "#FFFFFF"))
    render_title_zone(slide, spec, theme, safe)
    render_footer(slide, spec, theme, safe, total_slides)

    cfg = _layout(theme, "architecture_layered")
    header_col_px = cfg.get("header_column_px", 260)
    cell_columns = cfg.get("cell_columns", 6)
    layer_gap_px = cfg.get("layer_gap_px", 14)
    header_bg_token = cfg.get("header_background_token", "paper_3")
    header_name_px = cfg.get("header_name_size_px", 24)
    header_label_px = cfg.get("header_label_size_px", 14)
    cell_title_px = cfg.get("cell_title_size_px", 16)
    cell_desc_px = cfg.get("cell_desc_size_px", 14)

    top_pad, right_pad, bottom_pad, left_pad = _canvas_padding_in(theme)
    font = _font_family(spec, theme)

    area_left = left_pad
    area_top = top_pad + 1.4
    area_w = sw - area_left - right_pad
    area_h = sh - area_top - bottom_pad - 0.5

    layers = _extra(spec, "layers", default=None) or []
    if not layers:
        for p in get_points(spec):
            layers.append({
                "name": p.heading or "",
                "cells": [{"title": p.body or ""}],
            })
    n_layers = max(len(layers), 1)

    # 从 content (path Y) 取层, 补 cell.desc — variant (path X) 常只给 title, desc 落在 content
    _content = getattr(spec, "content", None)
    _content_layers = []
    if _content is not None:
        _content_layers = getattr(_content, "layers", None)
        if _content_layers is None:
            _content_layers = (getattr(_content, "__pydantic_extra__", None) or {}).get("layers", []) or []

    header_w = _px_in(header_col_px)
    gap_in = _px_in(layer_gap_px)
    layer_h = (area_h - gap_in * (n_layers - 1)) / n_layers
    cell_area_w = area_w - header_w - 0.15

    header_name_pt = _px_pt(header_name_px)
    header_label_pt = _px_pt(header_label_px)
    cell_title_pt = _px_pt(cell_title_px)
    cell_desc_pt = _px_pt(cell_desc_px)

    header_bg = _color(theme, header_bg_token, "#EAEAEA")
    paper_2 = _color(theme, "paper_2", "#F4F4F4")
    primary = _color(theme, "primary", "#C7000B")
    paper = _color(theme, "paper", "#FFFFFF")
    ink = _color(theme, "ink", "#1F1F1F")
    ink_soft = _color(theme, "ink_soft", "#4B4B4B")
    ink_mute = _color(theme, "ink_mute", "#9A9A9A")

    for li, layer in enumerate(layers):
        if isinstance(layer, str):
            layer = {"name": layer, "cells": []}
        y = area_top + li * (layer_h + gap_in)

        # Header 格
        _add_rect(slide, area_left, y, header_w, layer_h, header_bg)
        # schemas: layer.header.{code, name}; legacy: layer.{name, label}
        header_obj = _dget(layer, "header", default=None)
        if header_obj is not None:
            name_text = _dget(header_obj, "name", default="")
            label_text = _dget(header_obj, "code", default="") or f"L{li + 1}"
        else:
            name_text = _dget(layer, "name", default="")
            label_text = _dget(layer, "label", default="") or f"L{li + 1}"
        add_textbox(
            slide, area_left + 0.15, y + 0.15,
            header_w - 0.3, header_name_pt / 72 * 1.4 + 0.1,
            name_text, font, header_name_pt,
            ink, bold=True,
        )
        add_textbox(
            slide, area_left + 0.15,
            y + 0.15 + header_name_pt / 72 * 1.4 + 0.05,
            header_w - 0.3, header_label_pt / 72 * 1.4 + 0.05,
            label_text, font, header_label_pt,
            ink_mute,
        )

        # 右侧 cells (schemas 与 legacy 字段名一致)
        cells = _dget(layer, "cells", default=None) or []
        n_cells = len(cells) if cells else cell_columns
        cw = cell_area_w / max(n_cells, 1)
        for ci in range(n_cells):
            cell = cells[ci] if ci < len(cells) else {}
            if isinstance(cell, str):
                cell = {"title": cell}
            cx = area_left + header_w + 0.15 + ci * cw
            highlight = bool(_dget(cell, "highlight", default=False))
            fill = primary if highlight else paper_2
            _add_rect(slide, cx, y, cw - 0.05, layer_h, fill)

            ctitle = _dget(cell, "title", default="")
            cdesc = _dget(cell, "desc", "description", default="")
            if not cdesc and li < len(_content_layers):
                _ccells = _dget(_content_layers[li], "cells", default=None) or []
                if ci < len(_ccells):
                    cdesc = _dget(_ccells[ci], "desc", "description", default="")
            title_color = paper if highlight else ink
            desc_color = paper if highlight else ink_soft
            add_textbox(
                slide, cx + 0.1, y + 0.15,
                cw - 0.2, cell_title_pt / 72 * 1.5 + 0.1,
                ctitle, font, cell_title_pt,
                title_color, bold=True,
            )
            if cdesc:
                add_textbox(
                    slide, cx + 0.1,
                    y + 0.15 + cell_title_pt / 72 * 1.5 + 0.05,
                    cw - 0.2, layer_h - 0.3 - cell_title_pt / 72 * 1.5,
                    cdesc, font, cell_desc_pt,
                    desc_color,
                )


