"""内容量校验器 (S4 Phase 2 从 validate_plan.py 拆出)。

阈值常量 + 字符统计 helper + 按 visual_type 分组的内容量校验。
"""
from __future__ import annotations

# 华为主题 variant 视觉类型 — 单一来源, 从 schemas.variants import 防 drift (P2-A 审计教训)。
from schemas.variants import VARIANT_TYPES as VARIANT_EXEMPT_TYPES

from engine.validators.types import SlideResult, PointIssue


# ---------------------------------------------------------------------------
# 阈值配置
# ---------------------------------------------------------------------------

PER_POINT_MIN: dict[str, int] = {
    "cards": 80,
    "comparison": 100,
    "process": 80,
    "framework": 80,
    "timeline": 80,
}

TOTAL_MIN: dict[str, int] = {
    "bullets": 200,
    "data-contrast": 80,
    "table": 0,  # table 用行数校验
}

# 豁免类型（标题型页面，内容量不适用）
EXEMPT_TYPES = {"hero-statement", "quote-hero", "story-card"}

# table 最小行数
TABLE_MIN_ROWS = 2


# ---------------------------------------------------------------------------
# 分组 + 字符统计 helper
# ---------------------------------------------------------------------------

def _match_type_group(visual_type: str) -> str | None:
    """将 visual_type 映射到阈值组。"""
    if visual_type in EXEMPT_TYPES:
        return "exempt"
    # 华为 variant 的字数约束由 Pydantic min_length 提供，字数阈值在这里豁免
    if visual_type in VARIANT_EXEMPT_TYPES:
        return "variant"
    for prefix in PER_POINT_MIN:
        if visual_type.startswith(prefix):
            return prefix
    if visual_type in TOTAL_MIN:
        return visual_type
    return None


def _count_chars(text: str) -> int:
    """计算有效字符数（去除首尾空白）。"""
    return len(text.strip())


def _point_text(point) -> str:
    """Extract text from a key_point (str or StructuredPoint dict)."""
    if isinstance(point, str):
        return point
    if isinstance(point, dict):
        parts = []
        for key in ("heading", "body", "metric_value", "metric_label"):
            if point.get(key):
                parts.append(point[key])
        return " ".join(parts)
    return str(point)


def _point_body_chars(point) -> int:
    """Count body chars from a key_point (for per-point validation)."""
    if isinstance(point, str):
        return _count_chars(point)
    if isinstance(point, dict):
        return _count_chars(point.get("body", ""))
    return _count_chars(str(point))


def _total_content_chars(content: dict) -> int:
    """计算一页的总内容字符数。"""
    total = 0
    for key in ("title", "subtitle", "description", "body_text"):
        if content.get(key):
            total += _count_chars(content[key])
    for point in content.get("key_points") or []:
        total += _count_chars(_point_text(point))
    return total


# ---------------------------------------------------------------------------
# 内容量校验 (从 validate_slide 的非 variant 分支抽出)
# ---------------------------------------------------------------------------

def validate_content_volume(result: SlideResult, visual_type: str, content: dict, group):
    """按 group 校验内容量 (per-point / table / 整页总量)。mutate + return result。"""
    key_points = content.get("key_points") or []

    # 按 point 校验的类型
    if group in PER_POINT_MIN:
        min_per_point = PER_POINT_MIN[group]
        for i, point in enumerate(key_points):
            chars = _point_body_chars(point)
            text_preview = _point_text(point).strip()
            if chars < min_per_point:
                result.point_issues.append(PointIssue(
                    index=i + 1,
                    text=text_preview,
                    char_count=chars,
                    min_required=min_per_point,
                ))
        if result.point_issues:
            result.status = "FAIL"
        return result

    # table 校验
    if visual_type == "table":
        table_data = content.get("table_data") or {}
        headers = table_data.get("headers") or []
        rows = table_data.get("rows") or []
        issues = []
        if not headers:
            issues.append("headers 为空")
        if len(rows) < TABLE_MIN_ROWS:
            issues.append(f"rows={len(rows)} (min {TABLE_MIN_ROWS})")
        if issues:
            result.status = "FAIL"
            result.table_issue = "; ".join(issues)
        return result

    # 整页总量校验（bullets, data-contrast, 其他）
    if group in TOTAL_MIN:
        min_total = TOTAL_MIN[group]
    else:
        min_total = 150  # 兜底

    # key_points 的总字符（不含 title/subtitle）
    points_chars = sum(_point_body_chars(p) for p in key_points)
    body_chars = _count_chars(content.get("body_text") or "")
    content_chars = points_chars + body_chars

    if content_chars < min_total:
        result.status = "FAIL"
        result.total_issue = f"内容区 {content_chars} 字 (min {min_total})"

    return result

