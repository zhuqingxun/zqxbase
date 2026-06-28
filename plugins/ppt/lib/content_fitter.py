"""content_fitter.py: 向后兼容 shim — 实际逻辑迁到 lib/text_metrics.py.

2026-05-19 audit fix (ARCH-007): 历史上 estimate_text_overflow / suggest_font_size
散落在 content_fitter / render.py / renderers_huawei 三份独立实现, 公式不同, 改一份不动其它.
现统一到 lib/text_metrics.py (中英文加权), 此处仅 re-export 保持调用方 import 不破坏.
"""

from lib.text_metrics import estimate_text_overflow, suggest_font_size  # noqa: F401

__all__ = ["estimate_text_overflow", "suggest_font_size"]
