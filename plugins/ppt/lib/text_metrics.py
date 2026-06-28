"""text_metrics.py: 文本几何估算单一来源.

合并历史上散落 3 处的等价实现:
- lib/content_fitter.py:estimate_text_overflow  (chars_per_inch = 72/font_size * 1.0)
- engine/render.py:estimate_content_height       (同公式, padding=0.4)
- engine/renderers_huawei.py:_estimate_text_height_in  (cn 1.0 / en 0.55 加权, padding=0.15)

公式说明 (renderers_huawei 的精细版本为基础):
- 中文全角字符: width ≈ font_size (1 em), chars_per_inch ≈ 72/font_size
- 英文半角字符: 按 0.55 em 加权 (典型 sans-serif 字符 0.5-0.6 em)
- 混合文本: 总 "等效中文字数" = cn_count + (total - cn_count) * 0.55

历史教训 (2026-05-19 audit, ARCH-007): 三份独立实现, 改一份不会改其他, 维护噩梦.
huawei 渲染精度 (精细) 比通用 cards/bullets (粗糙) 高, 让主题间渲染质量不对等. 现统一.

注意保留旧函数 API (estimate_text_overflow / estimate_content_height) 以减小调用方改动.
"""

from __future__ import annotations

from functools import lru_cache


# ============================================================
# 字符加权
# ============================================================


@lru_cache(maxsize=256)
def weighted_char_count(text: str) -> float:
    """混合中英文文本的等效中文字数. 中文 1.0, 英文 0.55 em.

    @lru_cache 让重复计算同字符串只算一次 (title / heading 等常重复).
    """
    cn = sum(1 for ch in text if "一" <= ch <= "鿿")
    return cn + (len(text) - cn) * 0.55


# ============================================================
# 高度估算
# ============================================================


def estimate_text_lines(
    text: str,
    width_inches: float,
    font_size_pt: float,
) -> int:
    """估算 text 在给定 width / font_size 下需要的行数.

    每个 paragraph (按 \\n 切) 至少占 1 行. 空 paragraph 也算 1 行 (空行视觉占位).
    """
    if not text:
        return 0
    chars_per_in_cjk = 72.0 / max(font_size_pt, 1.0)
    chars_per_line_cjk_equiv = max(1, int(width_inches * chars_per_in_cjk))

    lines_needed = 0
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines_needed += 1
            continue
        w = weighted_char_count(paragraph)
        # ceil 整除
        lines_needed += max(1, -(-int(w + 0.5) // chars_per_line_cjk_equiv))
    return lines_needed


@lru_cache(maxsize=512)
def estimate_text_height_inches(
    text: str,
    width_inches: float,
    font_size_pt: float,
    line_spacing: float = 1.3,
    padding_inches: float = 0.15,
) -> float:
    """估算 text 在给定 width / font_size / 行距下需要的总高度 (英寸).

    包含上下 padding. 单位 inches. 默认 line_spacing=1.3 / padding=0.15 (huawei renderer 经验值).
    """
    lines = estimate_text_lines(text, width_inches, font_size_pt)
    if lines <= 0:
        return padding_inches * 2
    line_height_inches = font_size_pt / 72.0 * line_spacing
    return lines * line_height_inches + padding_inches * 2


# ============================================================
# 向后兼容 API (旧调用方继续工作)
# ============================================================


def estimate_text_overflow(
    text: str,
    width_inches: float,
    height_inches: float,
    font_size_pt: int = 16,
    line_spacing: float = 1.15,
) -> bool:
    """旧 API (lib/content_fitter): 判断 text 是否会溢出给定区域. 中英文加权后判断."""
    line_height_inches = font_size_pt / 72.0 * line_spacing
    max_lines = max(1, int(height_inches / line_height_inches))
    lines_needed = estimate_text_lines(text, width_inches, font_size_pt)
    return lines_needed > max_lines


def suggest_font_size(
    text: str,
    width_inches: float,
    height_inches: float,
    preferred_size_pt: int = 16,
    min_size_pt: int = 11,
    line_spacing: float = 1.15,
) -> int:
    """旧 API (lib/content_fitter): 从 preferred_size 起逐次缩小直到不溢出, 不低于 min_size."""
    for size in range(preferred_size_pt, min_size_pt - 1, -1):
        if not estimate_text_overflow(text, width_inches, height_inches, size, line_spacing):
            return size
    return min_size_pt
