"""反模式 + WARN 级检查 (S4 Phase 2 从 validate_plan.py 拆出)。均非阻塞。"""
from __future__ import annotations

from engine.validators.content_volume import EXEMPT_TYPES


def _check_slide_warnings(slide: dict) -> list[str]:
    """Check a single slide for WARN-level issues (non-blocking)."""
    warnings = []
    visual_type = slide.get("visual_type", "bullets")
    content = slide.get("content", {})

    if visual_type in EXEMPT_TYPES:
        return warnings

    # Missing description
    if not content.get("description"):
        warnings.append("missing description")

    key_points = content.get("key_points") or []

    # cards/comparison/process without heading
    for prefix in ("cards", "comparison", "process", "framework"):
        if visual_type.startswith(prefix):
            for i, pt in enumerate(key_points):
                if isinstance(pt, dict) and not pt.get("heading"):
                    warnings.append(f"point {i+1}: missing heading")
                elif isinstance(pt, str) and ": " not in pt:
                    warnings.append(f"point {i+1}: missing heading (plain string)")
            break

    # data-contrast without metric_value
    if visual_type == "data-contrast":
        for i, pt in enumerate(key_points):
            if isinstance(pt, dict) and not pt.get("metric_value"):
                warnings.append(f"point {i+1}: missing metric_value")

    return warnings


def validate_anti_patterns(slides: list[dict]) -> list[str]:
    """Detect plan-level anti-patterns (non-blocking warnings)."""
    warnings = []
    # Consecutive same visual_type
    for i in range(1, len(slides)):
        vt_prev = slides[i-1].get("visual_type", "")
        vt_curr = slides[i].get("visual_type", "")
        if vt_prev == vt_curr and vt_prev not in EXEMPT_TYPES:
            warnings.append(
                f"Slide {slides[i-1].get('id')}-{slides[i].get('id')}: "
                f"consecutive {vt_curr}"
            )
    return warnings

