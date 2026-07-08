"""validate_plan 校验器子模块包 (S4 Phase 2 god-module 拆分)。"""
from engine.validators.types import PointIssue, SlideResult  # noqa: F401
from engine.validators.content_volume import (  # noqa: F401
    PER_POINT_MIN, TOTAL_MIN, EXEMPT_TYPES, TABLE_MIN_ROWS, VARIANT_EXEMPT_TYPES,
    _match_type_group, _count_chars, _point_text, _point_body_chars,
    _total_content_chars, validate_content_volume,
)
from engine.validators.schema import validate_variant_schema, _lookup_variant_model  # noqa: F401
from engine.validators.anti_patterns import validate_anti_patterns, _check_slide_warnings  # noqa: F401
