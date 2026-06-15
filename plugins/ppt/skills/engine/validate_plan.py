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

# 华为主题 variant 视觉类型 — 单一来源 (P2-A 审计教训), ValidationReport 应用率口径用。
from schemas.variants import VARIANT_TYPES as VARIANT_EXEMPT_TYPES

# 校验器子模块 (S4 Phase 2 god-module 拆分)
from engine.validators.types import PointIssue, SlideResult  # noqa: F401
from engine.validators.content_volume import (  # noqa: F401
    _match_type_group, _total_content_chars, validate_content_volume,
)
from engine.validators.schema import validate_variant_schema
from engine.validators.anti_patterns import validate_anti_patterns, _check_slide_warnings


# ---------------------------------------------------------------------------
# 报告聚合数据结构
# ---------------------------------------------------------------------------

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

    @property
    def huawei_variant_count(self) -> int:
        """已选 huawei 18 版式的 slide 数（来自 VARIANT_EXEMPT_TYPES）."""
        return sum(1 for r in self.results if r.visual_type in VARIANT_EXEMPT_TYPES)

    @property
    def huawei_variant_ratio(self) -> float:
        """huawei 18 版式占比 = huawei_variant_count / total_slides."""
        if self.total_slides == 0:
            return 0.0
        return self.huawei_variant_count / self.total_slides

    def theme_application_status(
        self, warn_below: float = 0.60, fail_below: float = 0.30
    ) -> str:
        """根据占比分级: < fail_below=FAIL, < warn_below=WARN, 否则 PASS.

        阈值由 themes/<name>/preferences.yaml 的 application_thresholds 提供,
        默认 60/30 (Q5 决议)。
        """
        r = self.huawei_variant_ratio
        if r < fail_below:
            return "FAIL"
        if r < warn_below:
            return "WARN"
        return "PASS"

    def to_dict(self) -> dict:
        return {
            "plan_path": self.plan_path,
            "total_slides": self.total_slides,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "ok": self.ok,
            "huawei_variant_count": self.huawei_variant_count,
            "huawei_variant_ratio": round(self.huawei_variant_ratio, 4),
            "slides": [r.to_dict() for r in self.results],
        }



# ---------------------------------------------------------------------------
# 校验编排
# ---------------------------------------------------------------------------

def validate_slide(slide: dict) -> SlideResult:
    """校验单页 (编排: setup -> exempt -> variant schema 或 content volume)。"""
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

    # 豁免类型 (标题型页面)
    if group == "exempt":
        result.status = "SKIP"
        return result

    # 华为 variant: 按 schemas/variants.py 子模型严格校验 (path X)
    if group == "variant":
        return validate_variant_schema(slide, result, visual_type, content)

    # 其余: 按内容量校验 (per-point / table / 整页总量)
    return validate_content_volume(result, visual_type, content, group)


def validate_plan(plan_path: str) -> ValidationReport:
    """校验整份 slide-plan.yaml。"""
    return validate_plan_from_data(yaml.safe_load(Path(plan_path).read_text(encoding="utf-8")), plan_path)


def validate_plan_from_data(data: dict, plan_path: str = "") -> ValidationReport:
    """从已 load 的 data dict 校验. 用于 main 复用同一份 yaml.safe_load 结果, 避免大 plan 双解析."""
    slides = data.get("slides", []) if isinstance(data, dict) else []
    results = [validate_slide(s) for s in slides]
    return ValidationReport(
        plan_path=plan_path,
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

def load_theme_thresholds(theme_name: str) -> tuple[float, float]:
    """读 themes/<theme>/preferences.yaml 的 application_thresholds.

    优先用 engine.theme_loader (P2 引入的单一来源), 不可用时回退 engine.render.load_theme.
    任一加载失败均退回硬编码默认 60/30 (Q5 决议)。
    """
    warn_below, fail_below = 0.60, 0.30
    theme: dict | None = None
    try:
        from engine.theme_loader import load_theme as _load  # noqa: PLC0415
        theme = _load(theme_name)
    except Exception:
        try:
            from engine.render import load_theme as _load  # noqa: PLC0415
            theme = _load(theme_name)
        except Exception:
            theme = None
    if isinstance(theme, dict):
        thresholds = theme.get("preferences", {}).get("application_thresholds", {})
        if isinstance(thresholds, dict):
            warn_below = float(thresholds.get("warn_below", warn_below))
            fail_below = float(thresholds.get("fail_below", fail_below))
    return warn_below, fail_below


# 向后兼容 alias (S4 Phase 2 L4: 公有化前旧名, orchestrator/tests 过渡用)
_load_theme_thresholds = load_theme_thresholds


def main() -> None:
    parser = argparse.ArgumentParser(
        description="校验 slide-plan.yaml 内容量是否达标"
    )
    parser.add_argument("slide_plan", help="slide-plan.yaml 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument(
        "--theme",
        default=None,
        help="主题名称 (启用 theme 应用率门禁, 目前仅 huawei 主题有阈值)",
    )
    args = parser.parse_args()

    # 2026-05-19 audit fix: yaml.safe_load 单次提到顶部, validate_plan + warnings 复用同一份 data
    # (原版 validate_plan 内一次, main 内又 load 一次, 大 plan 50-200ms × 2).
    path = Path(args.slide_plan)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    report = validate_plan_from_data(data, str(path))

    # Collect warnings
    slides = data.get("slides", [])
    slide_warnings: dict[int, list[str]] = {}
    for s in slides:
        sid = s.get("id", 0)
        ws = _check_slide_warnings(s)
        if ws:
            slide_warnings[sid] = ws
    ap_warnings = validate_anti_patterns(slides)

    # huawei 应用率门禁 (仅当 --theme=huawei)
    application_status: str | None = None
    application_thresholds: tuple[float, float] | None = None
    if args.theme == "huawei":
        warn_below, fail_below = load_theme_thresholds(args.theme)
        application_thresholds = (warn_below, fail_below)
        application_status = report.theme_application_status(warn_below, fail_below)

    if args.json:
        out = report.to_dict()
        if slide_warnings:
            out["slide_warnings"] = slide_warnings
        if ap_warnings:
            out["anti_pattern_warnings"] = ap_warnings
        if application_status:
            warn_below, fail_below = application_thresholds
            out["theme_application"] = {
                "theme": args.theme,
                "status": application_status,
                "ratio": round(report.huawei_variant_ratio, 4),
                "huawei_count": report.huawei_variant_count,
                "total_slides": report.total_slides,
                "warn_below": warn_below,
                "fail_below": fail_below,
            }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report, slide_warnings, ap_warnings))
        if application_status:
            warn_below, fail_below = application_thresholds
            print()
            print(
                f"Theme Application: {args.theme} 18 variants in "
                f"{report.huawei_variant_count}/{report.total_slides} slides "
                f"({report.huawei_variant_ratio*100:.1f}%)"
            )
            print(
                f"  Status: {application_status} "
                f"(warn<{warn_below*100:.0f}% / fail<{fail_below*100:.0f}%)"
            )

    # exit code: 内容量 fail 退 1, 应用率 FAIL 退 2 (区分 PRD §7 二级门禁)
    if not report.ok:
        sys.exit(1)
    if application_status == "FAIL":
        warn_below, fail_below = application_thresholds
        print(
            f"\nACTION REQUIRED: {args.theme} 应用率 "
            f"{report.huawei_variant_ratio*100:.1f}% 低于 "
            f"{fail_below*100:.0f}% 门禁。Stage 3 LLM 应改选更多主题专属版式 "
            f"(参考 .theme-prompt.md), 或用户接受当前版本。"
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
