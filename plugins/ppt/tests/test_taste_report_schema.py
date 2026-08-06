# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=7.0", "pydantic>=2.0"]
# ///
"""taste JSON 输出契约回归 (S3-P1: feature-ppt-taste-json-anchor-validation).

校验 schemas/taste_report.py 的 TasteReport 契约 + baseline fixture 合规.

设计约束 (档位 A): taste 评分是 LLM 主观产出, **不可复现**, 故本套件只校验
*结构 / 字段齐全 / 数值边界 / 内部一致性*, **不做分数值回归** (不断言具体分数).
fixture 是真实 deck (renderer-deck.pptx, 2026-06-12 评审) 的双轴评审转写.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from pydantic import ValidationError  # noqa: E402
from schemas.taste_report import TasteReport, validate_taste_report_file  # noqa: E402

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "taste" / "renderer-deck.taste-report.json"
)


def _load_fixture_dict() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ============================================================
# baseline fixture 合规 (真实 deck 评审能被契约接受)
# ============================================================

def test_fixture_exists_and_validates():
    """真实 baseline fixture 必须能被 TasteReport 契约接受."""
    assert FIXTURE.exists(), f"fixture 缺失: {FIXTURE}"
    report = validate_taste_report_file(str(FIXTURE))
    assert report.pages == 19
    assert len(report.slides) == 19


def test_fixture_top_level_fields_present():
    """顶层字段齐全 (todo 要求: deck 级双轴均分 + mode + verdict)."""
    report = validate_taste_report_file(str(FIXTURE))
    assert report.deck
    assert report.timestamp
    assert report.mode in ("anchor", "general-principles")
    assert report.verdict
    assert report.summary.layout_avg > 0
    assert report.summary.palette_avg > 0


def test_fixture_slide_fields_complete():
    """逐页字段齐全 + 低分/AP 页必带 top_issue + suggestion (SKILL.md 惯例)."""
    report = validate_taste_report_file(str(FIXTURE))
    for s in report.slides:
        assert s.slide_type
        assert 1 <= s.layout_score <= 5
        assert 1 <= s.palette_score <= 5
        assert s.observation, f"slide {s.index} 缺 observation"
        if min(s.layout_score, s.palette_score) <= 3 or s.antipatterns:
            assert s.top_issue and s.suggestion, (
                f"slide {s.index} 低分/命中 AP 但缺 top_issue/suggestion"
            )


def test_fixture_summary_matches_slides():
    """summary 双轴均分与 slides 实际平均一致 (容差 0.01)."""
    d = _load_fixture_dict()
    slides = d["slides"]
    n = len(slides)
    la = sum(s["layout_score"] for s in slides) / n
    pa = sum(s["palette_score"] for s in slides) / n
    assert abs(d["summary"]["layout_avg"] - la) <= 0.01
    assert abs(d["summary"]["palette_avg"] - pa) <= 0.01


def test_fixture_antipattern_hits_declared_per_slide():
    """命中反模式汇总的每条都在对应页 slides[].antipatterns 中声明过."""
    report = validate_taste_report_file(str(FIXTURE))
    declared = {s.index: set(s.antipatterns) for s in report.slides}
    for hit in report.antipattern_hits:
        assert hit.ap in declared[hit.slide], (
            f"antipattern_hits slide={hit.slide} ap={hit.ap} 未在逐页声明"
        )


def test_fixture_improvements_reference_valid_slides():
    """改进项引用的 slides 序号都在 1..pages 范围内."""
    report = validate_taste_report_file(str(FIXTURE))
    valid = set(range(1, report.pages + 1))
    for imp in report.improvements:
        for sid in imp.slides:
            assert sid in valid, f"improvement rank={imp.rank} 引用越界页 {sid}"


# ============================================================
# 契约护栏: 非法输入必须被拒 (LLM 产出自相矛盾时 fail-loud)
# ============================================================

def test_rejects_score_out_of_range():
    d = _load_fixture_dict()
    d["slides"][0]["layout_score"] = 6
    with pytest.raises(ValidationError):
        TasteReport.model_validate(d)


def test_rejects_inconsistent_summary_avg():
    """篡改 summary.layout_avg 使其与 slides 实际平均不符 -> 拒."""
    d = _load_fixture_dict()
    d["summary"]["layout_avg"] = 2.0  # 实际 3.58
    with pytest.raises(ValidationError):
        TasteReport.model_validate(d)


def test_rejects_ap_hit_with_high_axis_scores():
    """命中 AP 却双轴均 > 2 (自相矛盾) -> 拒."""
    d = _load_fixture_dict()
    d["slides"][4]["antipatterns"] = ["AP1"]  # s5 layout=4 palette=4
    with pytest.raises(ValidationError):
        TasteReport.model_validate(d)


def test_rejects_extra_field():
    """extra=forbid: 多余字段 -> 拒 (与 ARCH-002 数据契约主线一致)."""
    d = _load_fixture_dict()
    d["slides"][0]["foobar"] = 1
    with pytest.raises(ValidationError):
        TasteReport.model_validate(d)


def test_rejects_pages_slides_length_mismatch():
    d = _load_fixture_dict()
    d["pages"] = 18  # slides 仍 19
    with pytest.raises(ValidationError):
        TasteReport.model_validate(d)


def test_rejects_undeclared_antipattern_hit():
    """antipattern_hits 引用一条逐页未声明的 AP -> 拒."""
    d = _load_fixture_dict()
    d["antipattern_hits"].append(
        {"slide": 5, "ap": "AP2", "description": "x", "fix": "y"}
    )
    with pytest.raises(ValidationError):
        TasteReport.model_validate(d)


def test_rejects_invalid_mode():
    d = _load_fixture_dict()
    d["mode"] = "freestyle"
    with pytest.raises(ValidationError):
        TasteReport.model_validate(d)


def test_rejects_noncontiguous_slide_index():
    """slides.index 必须连续 1..n -> 跳号被拒."""
    d = _load_fixture_dict()
    d["slides"][0]["index"] = 99
    with pytest.raises(ValidationError):
        TasteReport.model_validate(d)
