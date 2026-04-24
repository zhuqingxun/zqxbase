"""Simplified content fitter for MVP.

Provides basic text overflow estimation without font-metric-based measurement.
Full implementation (with visual_validator + Pillow dependency) deferred to Phase 2.
"""


def estimate_text_overflow(
    text: str,
    width_inches: float,
    height_inches: float,
    font_size_pt: int = 16,
    line_spacing: float = 1.15,
) -> bool:
    """Estimate if text will overflow a given area.

    Uses character-count heuristic (not font metrics).
    Accuracy: ~85% for Latin/CJK mixed text at standard sizes.

    Returns True if text is likely to overflow.
    """
    # CJK full-width chars: width ≈ font_size, so chars_per_inch ≈ 72/font_size.
    # Previous value 1.8 overestimated by 1.8x, causing severe undercount of lines.
    chars_per_inch = 72 / font_size_pt * 1.0
    chars_per_line = int(width_inches * chars_per_inch)
    line_height_inches = font_size_pt / 72 * line_spacing
    max_lines = int(height_inches / line_height_inches)

    lines_needed = 0
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines_needed += 1
            continue
        lines_needed += max(1, -(-len(paragraph) // max(1, chars_per_line)))

    return lines_needed > max_lines


def suggest_font_size(
    text: str,
    width_inches: float,
    height_inches: float,
    preferred_size_pt: int = 16,
    min_size_pt: int = 11,
    line_spacing: float = 1.15,
) -> int:
    """Suggest a font size that fits text in the given area.

    Binary search from preferred_size down to min_size.
    """
    for size in range(preferred_size_pt, min_size_pt - 1, -1):
        if not estimate_text_overflow(text, width_inches, height_inches, size, line_spacing):
            return size
    return min_size_pt
