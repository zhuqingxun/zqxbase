# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.0", "pyyaml>=6.0"]
# ///
"""validate_plan.py: 校验 slide-plan.yaml 的内容量是否达标。

按 visual type 检查每页字数:
- cards-N / process-N-phase / framework*: 每 key_point >= 80 字
- comparison-N: 每 key_point >= 100 字
- bullets: key_points 总计 >= 200 字
- data-contrast: 每 key_point >= 40 字
- table: rows >= 2 且 headers 非空
- hero-statement / quote-hero / story-card: 豁免（标题型页面）
- 其他: 总内容 >= 150 字

Usage:
    uv run --script engine/validate_plan.py <slide-plan.yaml>
    uv run --script engine/validate_plan.py <slide-plan.yaml> --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# 阈值配置
# ---------------------------------------------------------------------------

# 每 key_point 最小字符数
PER_POINT_MIN: dict[str, int] = {
    "cards": 80,
    "comparison": 100,
    "process": 80,
    "framework": 80,
    "timeline": 80,
}

# 整页最小总字符数
TOTAL_MIN: dict[str, int] = {
    "bullets": 200,
    "data-contrast": 80,
    "table": 0,  # table 用行数校验
}

# 豁免类型（标题型页面，内容量不适用）
EXEMPT_TYPES = {"hero-statement", "quote-hero", "story-card"}

# 华为主题 18 个 variant 视觉类型（走 Pydantic variant 校验，不用字数阈值）
VARIANT_EXEMPT_TYPES: set[str] = {
    "cover-left-bar", "toc", "section-divider-dark",
    "kpi-stats", "matrix-2x2", "architecture-layered",
    "timeline-huawei", "process-flow-huawei",
    "swot", "roadmap", "pyramid", "heatmap-matrix", "thankyou",
    "cards-6", "rings", "personas",
    "risk-list", "governance",
}

# table 最小行数
TABLE_MIN_ROWS = 2


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class PointIssue:
    """单个 key_point 的问题。"""
    index: int
    text: str
    char_count: int
    min_required: int

    @property
    def deficit(self) -> int:
        return max(0, self.min_required - self.char_count)


@dataclass
class SlideResult:
    """单页校验结果。"""
    slide_id: int
    visual_type: str
    title: str
    status: str  # "PASS" | "FAIL" | "SKIP"
    total_chars: int = 0
    point_issues: list[PointIssue] = field(default_factory=list)
    total_issue: str = ""  # 整页级别问题描述
    table_issue: str = ""

    def to_dict(self) -> dict:
        d: dict = {
            "slide_id": self.slide_id,
            "visual_type": self.visual_type,
            "title": self.title,
            "status": self.status,
            "total_chars": self.total_chars,
        }
        if self.point_issues:
            d["point_issues"] = [
                {
                    "index": p.index,
                    "chars": p.char_count,
                    "min": p.min_required,
                    "deficit": p.deficit,
                    "text_preview": p.text[:60] + ("..." if len(p.text) > 60 else ""),
                }
                for p in self.point_issues
            ]
        if self.total_issue:
            d["total_issue"] = self.total_issue
        if self.table_issue:
            d["table_issue"] = self.table_issue
        return d


@dataclass
class ValidationReport:
    """整份 plan 的校验报告。"""
    plan_path: str
    total_slides: int
    results: list[SlideResult]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "SKIP")

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict:
        return {
            "plan_path": self.plan_path,
            "total_slides": self.total_slides,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "ok": self.ok,
            "slides": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# 校验逻辑
# ---------------------------------------------------------------------------

_VARIANT_MODEL_CACHE: dict[str, type] | None = None


def _lookup_variant_model(visual_type: str) -> type:
    """按 visual_type 返回 schemas/variants.py 对应 Content 子模型类。

    首次调用时构建缓存；未找到抛 KeyError。
    """
    global _VARIANT_MODEL_CACHE
    if _VARIANT_MODEL_CACHE is None:
        from schemas import variants as _v  # 延迟导入避免循环
        cache: dict[str, type] = {}
        import inspect
        from pydantic import BaseModel
        for _name, _cls in inspect.getmembers(_v, inspect.isclass):
            if not issubclass(_cls, BaseModel) or _cls is BaseModel:
                continue
            vt_field = _cls.model_fields.get("visual_type")
            if vt_field is None:
                continue
            # Literal[...] 的取值位于 annotation 的 __args__
            anno = vt_field.annotation
            args = getattr(anno, "__args__", ())
            for literal_val in args:
                if isinstance(literal_val, str):
                    cache[literal_val] = _cls
        _VARIANT_MODEL_CACHE = cache
    return _VARIANT_MODEL_CACHE[visual_type]


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


def validate_slide(slide: dict) -> SlideResult:
    """校验单页内容量。"""
    slide_id = slide.get("id", 0)
    visual_type = slide.get("visual_type", "bullets")
    content = slide.get("content", {})
    title = content.get("title", "(untitled)")
    total_chars = _total_content_chars(content)

    result = SlideResult(
        slide_id=slide_id,
        visual_type=visual_type,
        title=title,
        status="PASS",
        total_chars=total_chars,
    )

    group = _match_type_group(visual_type)

    # 豁免类型
    if group == "exempt":
        result.status = "SKIP"
        return result

    # 华为 variant 校验：优先读 slide['variant']（Dev-1 renderer 读这里），
    # 缺失时回退从 content 顶层取字段子集。两条路径都按 visual_type 路由到
    # schemas/variants.py 对应子模型做严格校验（extra='forbid'）。
    if group == "variant":
        try:
            model_cls = _lookup_variant_model(visual_type)
        except KeyError:
            result.status = "FAIL"
            result.total_issue = f"visual_type '{visual_type}' 未注册 variant 子模型"
            return result

        variant_data = slide.get("variant")
        if variant_data is not None:
            # 路径 A：slide['variant'] 已提供（推荐路径）
            payload = dict(variant_data)
            payload.setdefault("visual_type", visual_type)
            source = "variant"
        else:
            # 路径 B：回退——从 content 取子模型声明字段子集 + 注入 discriminator
            declared_fields = set(model_cls.model_fields.keys()) - {"visual_type"}
            payload = {k: v for k, v in content.items() if k in declared_fields}
            payload["visual_type"] = visual_type
            source = "content"

        try:
            model_cls.model_validate(payload)
            result.status = "PASS"
        except Exception as exc:
            result.status = "FAIL"
            result.total_issue = (
                f"{source} 按 {model_cls.__name__} 校验失败: {exc.__class__.__name__}"
            )
        return result

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


def validate_plan(plan_path: str) -> ValidationReport:
    """校验整份 slide-plan.yaml。"""
    path = Path(plan_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    slides = data.get("slides", [])
    results = [validate_slide(s) for s in slides]
    return ValidationReport(
        plan_path=str(path),
        total_slides=len(slides),
        results=results,
    )


# ---------------------------------------------------------------------------
# 输出格式化
# ---------------------------------------------------------------------------

def format_text_report(report: ValidationReport, slide_warnings: dict[int, list[str]] = None,
                       anti_pattern_warnings: list[str] = None) -> str:
    """生成人类可读的校验报告。"""
    lines: list[str] = []
    lines.append(f"Validating {report.plan_path} ...")
    lines.append("")

    for r in report.results:
        tag = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}[r.status]
        lines.append(f"  {tag:4s}  Slide {r.slide_id:2d} ({r.visual_type}) \"{r.title}\"")

        if r.status == "SKIP":
            lines.append(f"        exempt visual type")
        elif r.point_issues:
            for p in r.point_issues:
                lines.append(
                    f"        Point {p.index}: {p.char_count} chars (min {p.min_required})"
                    f" — deficit {p.deficit}"
                )
        elif r.total_issue:
            lines.append(f"        {r.total_issue}")
        elif r.table_issue:
            lines.append(f"        {r.table_issue}")

        # Per-slide warnings
        if slide_warnings and r.slide_id in slide_warnings:
            for w in slide_warnings[r.slide_id]:
                lines.append(f"        WARN: {w}")

    # Anti-pattern warnings
    if anti_pattern_warnings:
        lines.append("")
        lines.append("Anti-pattern warnings:")
        for w in anti_pattern_warnings:
            lines.append(f"  WARN  {w}")

    lines.append("")
    lines.append(
        f"Summary: {report.passed} PASS / {report.failed} FAIL / {report.skipped} SKIP"
    )
    if not report.ok:
        lines.append(
            f"\nACTION REQUIRED: {report.failed} slides below content threshold."
            " Expand key_points with supporting detail, data, or examples."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="校验 slide-plan.yaml 内容量是否达标"
    )
    parser.add_argument("slide_plan", help="slide-plan.yaml 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    report = validate_plan(args.slide_plan)

    # Collect warnings
    path = Path(args.slide_plan)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    slides = data.get("slides", [])
    slide_warnings: dict[int, list[str]] = {}
    for s in slides:
        sid = s.get("id", 0)
        ws = _check_slide_warnings(s)
        if ws:
            slide_warnings[sid] = ws
    ap_warnings = validate_anti_patterns(slides)

    if args.json:
        out = report.to_dict()
        if slide_warnings:
            out["slide_warnings"] = slide_warnings
        if ap_warnings:
            out["anti_pattern_warnings"] = ap_warnings
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report, slide_warnings, ap_warnings))

    sys.exit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
