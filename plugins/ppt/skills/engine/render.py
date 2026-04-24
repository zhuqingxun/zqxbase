# /// script
# requires-python = ">=3.11"
# dependencies = ["python-pptx>=1.0.0", "pydantic>=2.0", "pyyaml>=6.0", "lxml>=4.9"]
# ///
"""render.py: Stage 4 - Deterministic PPTX rendering.

Consumes slide-plan.yaml, produces .pptx. NO AI involvement.
Same YAML input always produces same PPTX output.

Uses registry pattern: each visual type has a dedicated renderer function.

Usage:
    uv run --script engine/render.py <slide-plan.yaml> --theme <theme> --output output.pptx
    uv run --script engine/render.py <slide-plan.yaml> --theme <theme> --output output.pptx \
        --base-pptx existing.pptx --only-slides 3,5,7
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent.parent
# PEP 723 standalone script: add parent dir so `from lib.*` and `from schemas.*`
# resolve when executed via `uv run --script`. Not needed if imported as a library.
sys.path.insert(0, str(SKILLS_DIR))

from lib.pptx_compat import (
    qn, etree, make_sub_element, find_element,
    get_run_properties, get_paragraph_properties,
    OxmlElement, delete_slide,
)
from lib.font_fallback import resolve_font_for_pptx
from lib.margins import get_safe_area, enforce_margins, SafeArea
from lib.content_fitter import suggest_font_size, estimate_text_overflow
from schemas.slide_plan import SlidePlan, SlideSpec, SlideRole, StructuredPoint

# ===========================================================================
# THEME LOADING
# ===========================================================================

_REMOVED_THEMES: set[str] = {"clean-light", "academic", "dark-business"}
_DEFAULT_THEME: str = "huawei"


def load_theme(name: str | None) -> dict:
    """加载主题目录下的 tokens.yaml + layouts.yaml 合并字典。

    行为契约（PRD §7.3.1）：
    - name=None → 使用默认主题 huawei（INFO 日志）
    - name 在已删除清单（clean-light / academic / dark-business） → ValueError 硬报错
    - name 目录不存在 → FileNotFoundError 硬报错
    - 有效主题 → 读 tokens.yaml + layouts.yaml 浅合并

    返回 dict 结构：tokens 顶层键扁平（colors / fonts / type_scale_px 挂顶层，
    让旧 25 renderer 零改造），同时保留 `tokens` / `_layouts` 作为一级 key
    （新 renderer 显式读取）。

    顺序契约（SPEC-TL-13）：先判 removed 再检目录，顺序反了 FileNotFoundError
    会盖掉 removed 消息。
    """
    if name is None:
        logger.info("theme not specified, defaulting to '%s'", _DEFAULT_THEME)
        name = _DEFAULT_THEME
    if name in _REMOVED_THEMES:
        raise ValueError(
            f"theme '{name}' was removed in huawei-theme-complete release. "
            f"Use 'huawei' (the only supported theme). See release notes."
        )
    theme_dir = SKILLS_DIR / "themes" / name
    if not theme_dir.is_dir():
        themes_root = SKILLS_DIR / "themes"
        if themes_root.is_dir():
            available = sorted(p.name for p in themes_root.iterdir() if p.is_dir())
        else:
            available = []
        raise FileNotFoundError(
            f"theme '{name}' not found under themes/. Available: {available}"
        )
    tokens = yaml.safe_load((theme_dir / "tokens.yaml").read_text(encoding="utf-8")) or {}
    layouts = yaml.safe_load((theme_dir / "layouts.yaml").read_text(encoding="utf-8")) or {}
    return {"tokens": tokens, "layouts": layouts, **tokens, "_layouts": layouts}

# ===========================================================================
# RENDERER REGISTRY
# ===========================================================================

_RENDERERS: dict[str, callable] = {}

def register_renderer(visual_type: str):
    """Decorator to register a visual type renderer."""
    def wrapper(fn):
        _RENDERERS[visual_type] = fn
        return fn
    return wrapper

# ===========================================================================
# THEME HELPERS
# ===========================================================================

def _ve(theme: dict) -> dict:
    """Get visual_elements from theme with defaults."""
    defaults = {
        "footer_show_page_number": True,
        "footer_show_chapter": True,
        "footer_height_inches": 0.35,
        "card_header_height_inches": 0.4,
        "card_header_style": "color_bar",
        "card_content_alignment": "top",
        "card_show_number": False,
        "card_number_style": "circle",
        "card_number_size_pt": 22,
        "metric_container_style": "rounded_rect",
        "metric_value_size_pt": 44,
        "metric_label_size_pt": 14,
        "description_size_pt": 14,
        "description_color": None,
        "divider_below_title": False,
        "divider_color": "#E2E8F0",
    }
    ve = theme.get("visual_elements", {})
    return {**defaults, **ve}

# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================

def hex_to_rgb(hex_color: str) -> RGBColor:
    """Convert '#RRGGBB' to RGBColor."""
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def add_textbox(slide, left, top, width, height, text, font_name, font_size_pt, font_color, alignment=PP_ALIGN.LEFT, bold=False):
    """Add a text box with standard formatting."""
    txBox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.name = resolve_font_for_pptx(font_name)
    p.font.size = Pt(font_size_pt)
    p.font.color.rgb = hex_to_rgb(font_color)
    p.font.bold = bold
    p.alignment = alignment
    return txBox

def add_textbox_rich(slide, left, top, width, height, parts: list[dict], font_name: str, alignment=PP_ALIGN.LEFT):
    """Add a text box with mixed formatting (bold heading + regular body).

    parts: list of {"text": str, "size_pt": int, "color": str, "bold": bool}
    """
    txBox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = alignment
    for i, part in enumerate(parts):
        if i == 0:
            run = p.runs[0] if p.runs else p.add_run()
        else:
            run = p.add_run()
        run.text = part["text"]
        run.font.name = resolve_font_for_pptx(font_name)
        run.font.size = Pt(part["size_pt"])
        run.font.color.rgb = hex_to_rgb(part["color"])
        run.font.bold = part.get("bold", False)
    return txBox

def add_rounded_rect(slide, left, top, width, height, fill_color, corner_radius=0.1):
    """Add a rounded rectangle shape."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left), Inches(top), Inches(width), Inches(height),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = hex_to_rgb(fill_color)
    shape.line.fill.background()  # no border
    # Set corner radius via XML
    sp = shape._element
    prstGeom = sp.find(qn("a:prstGeom"))
    if prstGeom is not None:
        avLst = prstGeom.find(qn("a:avLst"))
        if avLst is None:
            avLst = etree.SubElement(prstGeom, qn("a:avLst"))
        gd = etree.SubElement(avLst, qn("a:gd"))
        radius_val = int(corner_radius / min(width, height) * 50000)
        gd.set("name", "adj")
        gd.set("fmla", f"val {radius_val}")
    return shape

def estimate_content_height(text: str, width_inches: float, font_size_pt: int,
                            line_spacing: float = 1.15, padding: float = 0.4) -> float:
    """Estimate the height needed to display text in a given width."""
    chars_per_inch = 72 / font_size_pt * 1.0  # CJK full-width
    chars_per_line = max(1, int(width_inches * chars_per_inch))
    line_height = font_size_pt / 72 * line_spacing
    lines = 0
    for para in text.split("\n"):
        if not para.strip():
            lines += 1
            continue
        lines += max(1, -(-len(para) // chars_per_line))
    return lines * line_height + padding


def compute_card_height(points: list[str], card_width: float, font_size_pt: int,
                        max_height: float, min_height: float = 1.5) -> float:
    """Compute card height that fits the tallest point, clamped to bounds."""
    usable_w = card_width - 0.3  # internal padding
    tallest = max(
        (estimate_content_height(p, usable_w, font_size_pt) for p in points),
        default=min_height,
    )
    return max(min_height, min(tallest, max_height))


def set_slide_background(slide, color_hex: str):
    """Set slide background color."""
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = hex_to_rgb(color_hex)


def normalize_point(p) -> StructuredPoint:
    """Normalize a key_point (str or dict or StructuredPoint) into StructuredPoint."""
    if isinstance(p, StructuredPoint):
        return p
    if isinstance(p, dict):
        return StructuredPoint(**p)
    if isinstance(p, str):
        if ": " in p:
            heading, body = p.split(": ", 1)
            return StructuredPoint(heading=heading.strip(), body=body.strip())
        return StructuredPoint(body=p)
    return StructuredPoint(body=str(p))


def get_points(spec: SlideSpec) -> list[StructuredPoint]:
    """Extract and normalize key_points from spec."""
    if not spec.content.key_points:
        return []
    return [normalize_point(p) for p in spec.content.key_points]


def get_point_bodies(points: list[StructuredPoint]) -> list[str]:
    """Extract body text from normalized points (for height calculation)."""
    return [p.body for p in points]

# ===========================================================================
# COMMON COMPONENTS
# ===========================================================================

def render_title_zone(slide, spec: SlideSpec, theme: dict, safe: SafeArea) -> float:
    """Render title + description. Returns total height used."""
    ve = _ve(theme)
    y = safe.top
    # Title
    add_textbox(
        slide, safe.left, y, safe.width, 0.6,
        spec.content.title, spec.design.font_family,
        spec.design.title_size_pt, spec.design.title_color,
        bold=True,
    )
    y += 0.6

    # Description (if present)
    desc = spec.content.description
    if desc:
        desc_color = ve["description_color"] or theme.get("colors", {}).get("text_secondary", spec.design.body_color)
        desc_size = ve["description_size_pt"]
        desc_h = estimate_content_height(desc, safe.width, desc_size, padding=0.15)
        desc_h = min(desc_h, 0.8)  # cap description height
        add_textbox(
            slide, safe.left, y + 0.05, safe.width, desc_h,
            desc, spec.design.font_family,
            desc_size, desc_color,
        )
        y += desc_h + 0.1

    # Optional divider line below title zone
    if ve.get("divider_below_title"):
        divider_color = ve.get("divider_color", "#E2E8F0")
        line = slide.shapes.add_connector(
            1,  # MSO_CONNECTOR.STRAIGHT
            Inches(safe.left), Inches(y + 0.02),
            Inches(safe.left + safe.width), Inches(y + 0.02),
        )
        line.line.color.rgb = hex_to_rgb(divider_color)
        line.line.width = Pt(0.75)
        y += 0.08

    return y - safe.top


def render_footer(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int) -> float:
    """Render footnote + page number footer. Returns footer height."""
    ve = _ve(theme)
    if not ve["footer_show_page_number"] and not spec.content.footnote:
        return 0.0

    footer_h = ve["footer_height_inches"]
    footer_top = safe.bottom - footer_h
    colors = theme.get("colors", {})
    footer_color = colors.get("text_secondary", spec.design.body_color)
    caption_size = theme.get("typography", {}).get("caption_size_pt", 10)

    # Footnote (left)
    if spec.content.footnote:
        add_textbox(
            slide, safe.left, footer_top, safe.width * 0.7, footer_h,
            spec.content.footnote, spec.design.font_family,
            caption_size, footer_color,
        )

    # Page number (right)
    if ve["footer_show_page_number"]:
        page_text = f"{spec.id} / {total_slides}"
        add_textbox(
            slide, safe.left + safe.width * 0.7, footer_top,
            safe.width * 0.3, footer_h,
            page_text, spec.design.font_family,
            caption_size, footer_color,
            alignment=PP_ALIGN.RIGHT,
        )

    return footer_h


def get_content_zone(safe: SafeArea, title_h: float, footer_h: float) -> tuple[float, float]:
    """Return (content_top, content_height) after title and footer."""
    content_top = safe.top + title_h + 0.15
    content_h = safe.height - title_h - footer_h - 0.3
    return content_top, max(content_h, 1.0)


# ===========================================================================
# CARD HEADER RENDERERS
# ===========================================================================

def _get_card_accent(theme: dict, spec: SlideSpec, index: int | None) -> str:
    """Pick accent color for a card: theme.colors.card_left_bar_colors[i] if available, else design.accent_color."""
    if index is None:
        return spec.design.accent_color
    bars = theme.get("colors", {}).get("card_left_bar_colors")
    if bars:
        return bars[index % len(bars)]
    return spec.design.accent_color


def render_card_header(slide, x, y, width, heading: str, theme: dict, spec: SlideSpec, index: int | None = None) -> float:
    """Render card header based on theme style. Returns header height (0 if no heading).

    Index enables per-card accent color from theme.colors.card_left_bar_colors.
    """
    if not heading:
        return 0.0
    ve = _ve(theme)
    style = ve["card_header_style"]
    header_h = ve["card_header_height_inches"]
    accent = _get_card_accent(theme, spec, index)

    if style == "color_bar":
        # Full-width color bar with white text
        add_rounded_rect(slide, x, y, width, header_h, accent,
                         corner_radius=theme.get("visual_preferences", {}).get("corner_radius_inches", 0.1))
        add_textbox(
            slide, x + 0.1, y + 0.05, width - 0.2, header_h - 0.1,
            heading, spec.design.font_family,
            spec.design.body_size_pt, "#FFFFFF",
            bold=True,
        )
        return header_h

    elif style == "left_bar":
        # Left accent bar + heading text on card background
        bar_w = 0.06
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(x), Inches(y), Inches(bar_w), Inches(header_h),
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = hex_to_rgb(accent)
        shape.line.fill.background()
        add_textbox(
            slide, x + bar_w + 0.1, y + 0.05, width - bar_w - 0.2, header_h - 0.1,
            heading, spec.design.font_family,
            spec.design.body_size_pt + 1, spec.design.title_color,
            bold=True,
        )
        return header_h

    else:  # "none" — bold text only
        add_textbox(
            slide, x + 0.15, y + 0.05, width - 0.3, header_h - 0.1,
            heading, spec.design.font_family,
            spec.design.body_size_pt, spec.design.title_color,
            bold=True,
        )
        return header_h


def render_card_number_badge(slide, x, y, theme: dict, spec: SlideSpec, index: int) -> None:
    """Render a number badge (01/02/03...) at the top-right corner of a card."""
    ve = _ve(theme)
    if not ve["card_show_number"]:
        return
    accent = _get_card_accent(theme, spec, index)
    size_pt = ve["card_number_size_pt"]
    style = ve["card_number_style"]
    num_text = f"{index + 1:02d}"

    if style == "circle":
        diameter = 0.5
        shape = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(x), Inches(y), Inches(diameter), Inches(diameter),
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = hex_to_rgb(accent)
        shape.line.fill.background()
        add_textbox(
            slide, x, y + 0.03, diameter, diameter - 0.06,
            num_text, spec.design.font_family,
            14, "#FFFFFF",
            alignment=PP_ALIGN.CENTER, bold=True,
        )
    else:  # plain
        add_textbox(
            slide, x, y, 0.7, 0.5,
            num_text, spec.design.font_family,
            size_pt, accent,
            bold=True,
        )


# ===========================================================================
# VISUAL TYPE RENDERERS
# ===========================================================================

@register_renderer("hero-statement")
def render_hero_statement(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int):
    """Single punchy statement, centered. No footer for title-type slides."""
    set_slide_background(slide, spec.design.background)
    add_textbox(
        slide, safe.left, safe.top + safe.height * 0.3,
        safe.width, safe.height * 0.3,
        spec.content.title, spec.design.font_family,
        spec.design.title_size_pt + 4, spec.design.title_color,
        alignment=PP_ALIGN.CENTER, bold=True,
    )
    if spec.content.subtitle:
        add_textbox(
            slide, safe.left, safe.top + safe.height * 0.6,
            safe.width, 0.5,
            spec.content.subtitle, spec.design.font_family,
            spec.design.body_size_pt, spec.design.body_color,
            alignment=PP_ALIGN.CENTER,
        )

@register_renderer("quote-hero")
def render_quote_hero(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int):
    """Powerful quote with attribution."""
    set_slide_background(slide, spec.design.background)
    add_textbox(
        slide, safe.left + 1, safe.top + safe.height * 0.25,
        safe.width - 2, safe.height * 0.35,
        f'\u201c{spec.content.title}\u201d', spec.design.font_family,
        spec.design.title_size_pt, spec.design.accent_color,
        alignment=PP_ALIGN.CENTER, bold=False,
    )
    if spec.content.subtitle:
        add_textbox(
            slide, safe.left + 1, safe.top + safe.height * 0.65,
            safe.width - 2, 0.5,
            f"-- {spec.content.subtitle}", spec.design.font_family,
            spec.design.body_size_pt, spec.design.body_color,
            alignment=PP_ALIGN.CENTER,
        )

@register_renderer("bullets")
def render_bullets(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int):
    """Bulleted content with title zone, bullet markers, and footer."""
    set_slide_background(slide, spec.design.background)
    title_h = render_title_zone(slide, spec, theme, safe)
    footer_h = render_footer(slide, spec, theme, safe, total_slides)
    content_top, content_h = get_content_zone(safe, title_h, footer_h)

    points = get_points(spec)
    if not points:
        return

    bullet_w = safe.width - 0.5
    gap = 0.12
    y = content_top

    for pt in points:
        # Bullet marker (small filled circle)
        marker_size = 0.08
        marker_y = y + spec.design.body_size_pt / 72 * 0.4
        shape = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(safe.left + 0.15), Inches(marker_y),
            Inches(marker_size), Inches(marker_size),
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = hex_to_rgb(spec.design.accent_color)
        shape.line.fill.background()

        # Text
        if pt.heading:
            text = f"{pt.heading}\n{pt.body}"
            parts = [
                {"text": pt.heading, "size_pt": spec.design.body_size_pt, "color": spec.design.title_color, "bold": True},
                {"text": f"\n{pt.body}", "size_pt": spec.design.body_size_pt, "color": spec.design.body_color, "bold": False},
            ]
            h = estimate_content_height(text, bullet_w, spec.design.body_size_pt)
            add_textbox_rich(slide, safe.left + 0.5, y, bullet_w, h, parts, spec.design.font_family)
        else:
            h = estimate_content_height(pt.body, bullet_w, spec.design.body_size_pt)
            add_textbox(
                slide, safe.left + 0.5, y, bullet_w, h,
                pt.body, spec.design.font_family,
                spec.design.body_size_pt, spec.design.body_color,
            )
        y += h + gap
        if y > content_top + content_h:
            break


# Cards renderer (cards-2 through cards-5)
def _render_cards(slide, spec: SlideSpec, theme: dict, safe: SafeArea, n_cards: int, total_slides: int):
    """N-column card layout with optional card headers."""
    set_slide_background(slide, spec.design.background)
    title_h = render_title_zone(slide, spec, theme, safe)
    footer_h = render_footer(slide, spec, theme, safe, total_slides)
    content_top, content_h = get_content_zone(safe, title_h, footer_h)

    ve = _ve(theme)
    colors = theme.get("colors", {}).get("card_fills", ["#F0F4FF"] * 5)
    gap = theme.get("spacing", {}).get("element_gap_inches", 0.25)
    card_width = (safe.width - gap * (n_cards - 1)) / n_cards
    corner_r = theme.get("visual_preferences", {}).get("corner_radius_inches", 0.1)

    points = get_points(spec)
    bodies = get_point_bodies(points)
    has_headers = any(p.heading for p in points)
    header_h = ve["card_header_height_inches"] if has_headers else 0.0

    # Content-aware card height
    max_card_height = content_h
    body_height = compute_card_height(
        bodies, card_width, spec.design.body_size_pt, max_card_height - header_h,
    ) if bodies else 2.0
    card_height = min(body_height + header_h, max_card_height)

    # Top-aligned cards (no vertical centering)
    card_top = content_top
    if ve["card_content_alignment"] == "center":
        card_top = content_top + max(0, (content_h - card_height) / 2)

    show_number = ve["card_show_number"]
    for i in range(n_cards):
        x = safe.left + i * (card_width + gap)
        fill = colors[i % len(colors)]
        use_rounded = theme.get("visual_preferences", {}).get("rounded_corners", True)

        # Card background
        if use_rounded:
            add_rounded_rect(slide, x, card_top, card_width, card_height, fill, corner_r)
        else:
            shape = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(x), Inches(card_top),
                Inches(card_width), Inches(card_height),
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = hex_to_rgb(fill)
            shape.line.fill.background()

        # Card header (per-card accent from theme.colors.card_left_bar_colors)
        pt = points[i] if i < len(points) else StructuredPoint(body="")
        h_used = render_card_header(slide, x, card_top, card_width, pt.heading, theme, spec, index=i)

        # Number badge (top-right corner, overlays on card)
        if show_number:
            badge_size = 0.5
            render_card_number_badge(
                slide, x + card_width - badge_size - 0.12, card_top - 0.12,
                theme, spec, index=i,
            )

        # Card body text — top-aligned
        text = pt.body
        body_top = card_top + h_used + 0.12
        body_avail = card_height - h_used - 0.22
        add_textbox(
            slide, x + 0.2, body_top,
            card_width - 0.4, body_avail,
            text, spec.design.font_family,
            spec.design.body_size_pt, spec.design.body_color,
        )

for n in range(2, 6):
    _RENDERERS[f"cards-{n}"] = lambda s, sp, t, sa, ts, _n=n: _render_cards(s, sp, t, sa, _n, ts)

# Comparison renderer (comparison-2 through comparison-5)
def _render_comparison(slide, spec: SlideSpec, theme: dict, safe: SafeArea, n_cols: int, total_slides: int):
    """N-column comparison layout with header row."""
    set_slide_background(slide, spec.design.background)
    title_h = render_title_zone(slide, spec, theme, safe)
    footer_h = render_footer(slide, spec, theme, safe, total_slides)
    content_top, content_h = get_content_zone(safe, title_h, footer_h)

    colors = theme.get("colors", {}).get("card_fills", ["#F0F4FF"] * 5)
    gap = theme.get("spacing", {}).get("element_gap_inches", 0.25)
    col_width = (safe.width - gap * (n_cols - 1)) / n_cols
    corner_r = theme.get("visual_preferences", {}).get("corner_radius_inches", 0.1)

    points = get_points(spec)
    bodies = get_point_bodies(points)

    header_height = 0.5
    max_body_height = content_h - header_height - 0.15
    body_height = compute_card_height(
        bodies, col_width, spec.design.body_size_pt, max_body_height,
    ) if bodies else max_body_height

    header_top = content_top
    body_top = header_top + header_height + 0.1

    for i in range(n_cols):
        x = safe.left + i * (col_width + gap)
        fill = colors[i % len(colors)]
        pt = points[i] if i < len(points) else StructuredPoint(body="")

        # Header bar
        header_text = pt.heading or f"Option {i+1}"
        add_rounded_rect(slide, x, header_top, col_width, header_height, spec.design.accent_color, corner_r)
        add_textbox(
            slide, x + 0.1, header_top + 0.05,
            col_width - 0.2, header_height - 0.1,
            header_text, spec.design.font_family,
            spec.design.body_size_pt, "#FFFFFF",
            alignment=PP_ALIGN.CENTER, bold=True,
        )
        # Body card
        add_rounded_rect(slide, x, body_top, col_width, body_height, fill, corner_r)
        body_text = pt.body
        add_textbox(
            slide, x + 0.15, body_top + 0.15,
            col_width - 0.3, body_height - 0.3,
            body_text, spec.design.font_family,
            spec.design.body_size_pt, spec.design.body_color,
        )

for n in range(2, 6):
    _RENDERERS[f"comparison-{n}"] = lambda s, sp, t, sa, ts, _n=n: _render_comparison(s, sp, t, sa, _n, ts)

# Process renderer (process-2-phase through process-5-phase)
def _render_process(slide, spec: SlideSpec, theme: dict, safe: SafeArea, n_phases: int, total_slides: int):
    """N-phase process flow with arrow connectors."""
    set_slide_background(slide, spec.design.background)
    title_h = render_title_zone(slide, spec, theme, safe)
    footer_h = render_footer(slide, spec, theme, safe, total_slides)
    content_top, content_h = get_content_zone(safe, title_h, footer_h)

    colors = theme.get("colors", {}).get("card_fills", ["#F0F4FF"] * 5)
    gap = theme.get("spacing", {}).get("element_gap_inches", 0.25)
    arrow_width = 0.3
    total_arrow_space = arrow_width * (n_phases - 1)
    phase_width = (safe.width - gap * (n_phases - 1) - total_arrow_space) / n_phases
    corner_r = theme.get("visual_preferences", {}).get("corner_radius_inches", 0.1)

    points = get_points(spec)
    bodies = get_point_bodies(points)

    # Content-aware phase height
    max_phase_height = content_h
    phase_height = compute_card_height(
        bodies, phase_width, spec.design.body_size_pt, max_phase_height, min_height=2.0,
    ) + 0.6 if bodies else max_phase_height
    phase_height = min(phase_height, max_phase_height)
    phase_top = content_top

    for i in range(n_phases):
        x = safe.left + i * (phase_width + gap + arrow_width)
        fill = colors[i % len(colors)]
        pt = points[i] if i < len(points) else StructuredPoint(body="")

        # Phase box
        add_rounded_rect(slide, x, phase_top, phase_width, phase_height, fill, corner_r)

        # Phase heading (from StructuredPoint.heading or fallback to "Phase N")
        heading = pt.heading or f"Phase {i+1}"
        add_textbox(
            slide, x + 0.15, phase_top + 0.1,
            phase_width - 0.3, 0.4,
            heading, spec.design.font_family,
            spec.design.body_size_pt + 2, spec.design.accent_color,
            bold=True,
        )
        # Phase body
        text = pt.body
        body_start = phase_top + 0.6
        body_avail = phase_height - 0.7
        add_textbox(
            slide, x + 0.15, body_start,
            phase_width - 0.3, body_avail,
            text, spec.design.font_family,
            spec.design.body_size_pt, spec.design.body_color,
        )
        # Arrow connector (except after last phase)
        if i < n_phases - 1:
            arrow_x = x + phase_width + gap * 0.3
            arrow_y = phase_top + phase_height / 2 - 0.2
            shape = slide.shapes.add_shape(
                MSO_SHAPE.RIGHT_ARROW, Inches(arrow_x), Inches(arrow_y),
                Inches(arrow_width), Inches(0.4),
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = hex_to_rgb(spec.design.accent_color)
            shape.line.fill.background()

for n in range(2, 6):
    _RENDERERS[f"process-{n}-phase"] = lambda s, sp, t, sa, ts, _n=n: _render_process(s, sp, t, sa, _n, ts)

@register_renderer("data-contrast")
def render_data_contrast(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int):
    """Two large metrics side by side with containers and body text."""
    set_slide_background(slide, spec.design.background)
    title_h = render_title_zone(slide, spec, theme, safe)
    footer_h = render_footer(slide, spec, theme, safe, total_slides)
    content_top, content_h = get_content_zone(safe, title_h, footer_h)

    ve = _ve(theme)
    colors = theme.get("colors", {}).get("card_fills", ["#F0F4FF"] * 5)
    gap = theme.get("spacing", {}).get("element_gap_inches", 0.25)
    corner_r = theme.get("visual_preferences", {}).get("corner_radius_inches", 0.1)

    points = get_points(spec)
    half_w = (safe.width - gap) / 2
    metric_size = ve["metric_value_size_pt"]
    label_size = ve["metric_label_size_pt"]
    container_style = ve["metric_container_style"]

    for i in range(min(2, len(points) if points else 0)):
        pt = points[i]
        x = safe.left + i * (half_w + gap)

        if pt.metric_value and container_style != "none":
            # Metric container
            container_h = 2.2
            fill = colors[i % len(colors)]
            if container_style == "circle":
                # Circle container
                circle_size = min(half_w * 0.6, container_h)
                cx = x + (half_w - circle_size) / 2
                shape = slide.shapes.add_shape(
                    MSO_SHAPE.OVAL,
                    Inches(cx), Inches(content_top), Inches(circle_size), Inches(circle_size),
                )
                shape.fill.solid()
                shape.fill.fore_color.rgb = hex_to_rgb(fill)
                shape.line.fill.background()
            else:
                # Rounded rect container
                add_rounded_rect(slide, x, content_top, half_w, container_h, fill, corner_r)

            # Metric value (large, centered)
            add_textbox(
                slide, x, content_top + 0.3, half_w, 1.0,
                pt.metric_value, spec.design.font_family,
                metric_size, spec.design.accent_color,
                alignment=PP_ALIGN.CENTER, bold=True,
            )
            # Metric label (small, centered, below value)
            label = pt.metric_label or pt.heading or ""
            if label:
                add_textbox(
                    slide, x + 0.1, content_top + 1.3, half_w - 0.2, 0.6,
                    label, spec.design.font_family,
                    label_size, spec.design.body_color,
                    alignment=PP_ALIGN.CENTER,
                )
            # Body text below container
            if pt.body:
                body_top = content_top + container_h + 0.2
                body_h = content_h - container_h - 0.3
                if body_h > 0.3:
                    add_textbox(
                        slide, x + 0.1, body_top, half_w - 0.2, body_h,
                        pt.body, spec.design.font_family,
                        spec.design.body_size_pt, spec.design.body_color,
                    )
        else:
            # Fallback: large text (backwards compat with plain strings)
            add_textbox(
                slide, x, content_top + 0.5, half_w, 2.0,
                pt.metric_value or pt.body, spec.design.font_family,
                metric_size, spec.design.accent_color,
                alignment=PP_ALIGN.CENTER, bold=True,
            )
            if pt.body and pt.metric_value:
                add_textbox(
                    slide, x + 0.1, content_top + 2.8, half_w - 0.2, content_h - 3.0,
                    pt.body, spec.design.font_family,
                    spec.design.body_size_pt, spec.design.body_color,
                )

@register_renderer("table")
def render_table(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int):
    """Table from table_data."""
    set_slide_background(slide, spec.design.background)
    title_h = render_title_zone(slide, spec, theme, safe)
    footer_h = render_footer(slide, spec, theme, safe, total_slides)
    content_top, content_h = get_content_zone(safe, title_h, footer_h)

    td = spec.content.table_data
    if not td:
        return
    rows = len(td.rows) + 1  # +1 for header
    cols = len(td.headers) if td.headers else (len(td.rows[0]) if td.rows else 1)
    table_shape = slide.shapes.add_table(
        rows, cols,
        Inches(safe.left), Inches(content_top),
        Inches(safe.width), Inches(min(content_h, rows * 0.5)),
    )
    tbl = table_shape.table
    for j, h in enumerate(td.headers):
        cell = tbl.cell(0, j)
        cell.text = h
    for i, row in enumerate(td.rows):
        for j, val in enumerate(row):
            if j < cols:
                tbl.cell(i + 1, j).text = str(val)

@register_renderer("comparison-tables")
def render_comparison_tables(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int):
    """Side-by-side comparison tables."""
    set_slide_background(slide, spec.design.background)
    title_h = render_title_zone(slide, spec, theme, safe)
    footer_h = render_footer(slide, spec, theme, safe, total_slides)
    content_top, content_h = get_content_zone(safe, title_h, footer_h)

    if spec.content.key_points:
        points = get_points(spec)
        y = content_top
        for pt in points:
            text = f"{pt.heading}: {pt.body}" if pt.heading else pt.body
            add_textbox(
                slide, safe.left + 0.3, y,
                safe.width - 0.3, 0.4,
                f"  {text}", spec.design.font_family,
                spec.design.body_size_pt, spec.design.body_color,
            )
            y += 0.5

@register_renderer("timeline-horizontal")
def render_timeline(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int):
    """Horizontal timeline with nodes."""
    set_slide_background(slide, spec.design.background)
    title_h = render_title_zone(slide, spec, theme, safe)
    footer_h = render_footer(slide, spec, theme, safe, total_slides)
    content_top, content_h = get_content_zone(safe, title_h, footer_h)

    points = get_points(spec)
    n = len(points) or 1
    node_y = content_top + content_h * 0.3
    for i, pt in enumerate(points):
        x = safe.left + i * safe.width / n + safe.width / n / 2 - 0.3
        # Node circle
        shape = slide.shapes.add_shape(
            MSO_SHAPE.OVAL, Inches(x), Inches(node_y), Inches(0.6), Inches(0.6),
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = hex_to_rgb(spec.design.accent_color)
        shape.line.fill.background()
        # Label
        label = pt.heading or pt.body
        add_textbox(
            slide, x - 0.5, node_y + 0.8, 1.6, 0.8,
            label, spec.design.font_family,
            spec.design.body_size_pt - 2, spec.design.body_color,
            alignment=PP_ALIGN.CENTER,
        )

@register_renderer("story-card")
def render_story_card(slide, spec: SlideSpec, theme: dict, safe: SafeArea, total_slides: int):
    """Full-bleed background with text overlay."""
    set_slide_background(slide, spec.design.background)
    overlay_height = safe.height * 0.4
    overlay_top = safe.top + safe.height - overlay_height
    add_rounded_rect(
        slide, safe.left, overlay_top, safe.width, overlay_height,
        "#000000", corner_radius=0.0,
    )
    add_textbox(
        slide, safe.left + 0.5, overlay_top + 0.3,
        safe.width - 1, 0.6,
        spec.content.title, spec.design.font_family,
        spec.design.title_size_pt, "#FFFFFF",
        bold=True,
    )
    if spec.content.body_text or spec.content.key_points:
        points = get_points(spec)
        text = spec.content.body_text or "\n".join(p.body for p in points)
        add_textbox(
            slide, safe.left + 0.5, overlay_top + 1.0,
            safe.width - 1, overlay_height - 1.3,
            text, spec.design.font_family,
            spec.design.body_size_pt, "#CCCCCC",
        )

# Framework renderers
def _render_framework(slide, spec: SlideSpec, theme: dict, safe: SafeArea, n_cols: int, total_slides: int):
    """Framework layout with optional columns and card headers."""
    set_slide_background(slide, spec.design.background)
    title_h = render_title_zone(slide, spec, theme, safe)
    footer_h = render_footer(slide, spec, theme, safe, total_slides)
    content_top, content_h = get_content_zone(safe, title_h, footer_h)

    ve = _ve(theme)
    colors = theme.get("colors", {}).get("card_fills", ["#F0F4FF"] * 5)
    gap = theme.get("spacing", {}).get("element_gap_inches", 0.25)
    col_width = (safe.width - gap * (n_cols - 1)) / n_cols
    corner_r = theme.get("visual_preferences", {}).get("corner_radius_inches", 0.1)

    points = get_points(spec)
    bodies = get_point_bodies(points)
    has_headers = any(p.heading for p in points)
    header_h = ve["card_header_height_inches"] if has_headers else 0.0

    max_col_height = content_h
    body_height = compute_card_height(
        bodies, col_width, spec.design.body_size_pt, max_col_height - header_h,
    ) if bodies else 2.0
    col_height = min(body_height + header_h, max_col_height)
    col_top = content_top

    for i in range(n_cols):
        x = safe.left + i * (col_width + gap)
        fill = colors[i % len(colors)]
        add_rounded_rect(slide, x, col_top, col_width, col_height, fill, corner_r)

        pt = points[i] if i < len(points) else StructuredPoint(body="")
        h_used = render_card_header(slide, x, col_top, col_width, pt.heading, theme, spec)

        add_textbox(
            slide, x + 0.2, col_top + h_used + 0.1,
            col_width - 0.4, col_height - h_used - 0.2,
            pt.body, spec.design.font_family,
            spec.design.body_size_pt, spec.design.body_color,
        )

_RENDERERS["framework"] = lambda s, sp, t, sa, ts: _render_framework(s, sp, t, sa, 1, ts)
_RENDERERS["framework-2col"] = lambda s, sp, t, sa, ts: _render_framework(s, sp, t, sa, 2, ts)
_RENDERERS["framework-3col"] = lambda s, sp, t, sa, ts: _render_framework(s, sp, t, sa, 3, ts)
_RENDERERS["framework-4col"] = lambda s, sp, t, sa, ts: _render_framework(s, sp, t, sa, 4, ts)

# 华为主题 renderer 注册：必须放在 _RENDERERS 所有旧条目填充完之后，避免循环 import
# （renderers_huawei 需要 register_renderer + helpers，render.py 再反 import 它）
from engine import renderers_huawei  # noqa: F401, E402

# ===========================================================================
# MAIN RENDERING PIPELINE
# ===========================================================================

def _get_blank_layout(prs: Presentation):
    """Find a blank slide layout, tolerant of custom templates."""
    for layout in prs.slide_layouts:
        if "blank" in layout.name.lower():
            return layout
    return prs.slide_layouts[len(prs.slide_layouts) - 1]


def render_slide(prs: Presentation, spec: SlideSpec, theme: dict, total_slides: int):
    """Render a single slide based on its visual_type."""
    slide_layout = _get_blank_layout(prs)
    slide = prs.slides.add_slide(slide_layout)
    safe = get_safe_area(
        {"left": theme.get("spacing", {}).get("slide_margin_inches", 0.5),
         "top": theme.get("spacing", {}).get("slide_margin_inches", 0.5),
         "right": theme.get("spacing", {}).get("slide_margin_inches", 0.5),
         "bottom": theme.get("spacing", {}).get("slide_margin_inches", 0.5)},
    )
    renderer = _RENDERERS.get(spec.visual_type, _RENDERERS.get("bullets"))
    if renderer:
        renderer(slide, spec, theme, safe, total_slides)
    return slide


def render_presentation(plan: SlidePlan, theme: dict, output_path: str,
                        base_pptx: str = None, only_slides: list[int] = None):
    """Render full presentation from slide plan."""
    if base_pptx:
        prs = Presentation(base_pptx)
    else:
        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

    if base_pptx and only_slides:
        indices_to_delete = sorted(
            [sid - 1 for sid in only_slides if 0 < sid <= len(prs.slides)],
            reverse=True,
        )
        for idx in indices_to_delete:
            delete_slide(prs, idx)

    total_slides = plan.narrative.total_slides
    for spec in plan.slides:
        if only_slides and spec.id not in only_slides:
            continue
        render_slide(prs, spec, theme, total_slides)

    # Windows file lock protection
    try:
        prs.save(output_path)
    except PermissionError:
        import os
        base, ext = os.path.splitext(output_path)
        for v in range(2, 10):
            alt = f"{base}_v{v}{ext}"
            try:
                prs.save(alt)
                print(f"Saved to {alt} (original path locked)")
                return
            except PermissionError:
                continue
        raise


def main():
    parser = argparse.ArgumentParser(description="Render PPTX from slide-plan.yaml")
    parser.add_argument("slide_plan", help="Path to slide-plan.yaml")
    parser.add_argument("--theme", default=None,
                        help="theme name (default: huawei if omitted)")
    parser.add_argument("--output", default="output.pptx")
    parser.add_argument("--base-pptx", default=None)
    parser.add_argument("--only-slides", default=None,
                        help="Comma-separated slide IDs to render")
    args = parser.parse_args()

    plan = SlidePlan.from_yaml(args.slide_plan)
    theme = load_theme(args.theme)
    only = [int(x) for x in args.only_slides.split(",")] if args.only_slides else None
    render_presentation(plan, theme, args.output, args.base_pptx, only)
    print(f"Rendered {len(plan.slides)} slides to {args.output}")


if __name__ == "__main__":
    main()
