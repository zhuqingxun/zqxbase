"""向后兼容 shim (S4 Phase 1): 18 个 huawei renderer 已拆到 engine/renderers/huawei/<vt>.py。

保留旧 import 路径:
  - `from engine import renderers_huawei` (触发注册 + 旧调用方)
  - `from engine.renderers_huawei import _extra` (tests/variants/test_extra_dual_path.py)
helper 单一来源在 engine.renderer_kit; renderer 在 engine.renderers.huawei 包。
"""
from engine.renderers import huawei  # noqa: F401  触发 18 renderer 注册
from engine.renderer_kit import (  # noqa: F401  向后兼容 helper import 路径
    _px_pt, _px_in, _tokens, _layouts, _color, _lerp_hex, _is_dark, _type_px, _layout,
    _extra, _extra_list_merge, _estimate_text_height_in, _dget, _add_rect,
    _canvas_dims_in, _canvas_padding_in, _slide_dims_in, _font_family, TREND_COLOR_TOKEN,
)
