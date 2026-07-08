# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.0"]
# ///
"""taste_report.py: ppt:taste 结构化 JSON 输出契约 (S3-P1).

ppt:taste skill 在 markdown 报告 (.taste-report.md) 外额外产出结构化
.taste-report.json. 本模块是该 JSON 的 schema **单一来源**:
  - skills/taste/SKILL.md 的 JSON 字段说明引用本契约
  - skill 运行时 Step 4c 用本文件的 CLI 自校验 (fail-loud)
  - tests/test_taste_report_schema.py 校验 baseline fixture

设计约束 (S3-P1 档位 A):
  taste 评分是 LLM 主观产出, **不可复现**, 故本契约只约束 *结构 / 字段齐全 /
  数值边界 / 内部一致性*, 绝不约束分数值本身 (不做分数回归 CI 门).
  内部一致性校验 (summary 与 slides 自洽 / antipattern_hits 与逐页声明自洽)
  是给 LLM 产出的强护栏 — 防止 "给了 AP 又给高分" 这类自相矛盾.

Usage (skill 自校验 / CI):
    uv run --script schemas/taste_report.py <path-to.taste-report.json>
"""
from __future__ import annotations

import argparse
import json
import sys

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SlideScore(BaseModel):
    """单页双轴评分 + 观察 (对应 markdown 报告 '逐页评分' 表的一行)."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)  # slide 序号 (1-based)
    slide_type: str  # 语义型 (cover/toc/content/...) 或 renderer 型 (kpi-stats/...)
    layout_score: int = Field(ge=1, le=5)
    palette_score: int = Field(ge=1, le=5)
    # 命中的反模式编号, 如 ["AP4"]. 无反模式 = 空数组 [] (绝不写 ["—"]).
    antipatterns: list[str] = Field(default_factory=list)
    observation: str = ""  # 1-2 句具体观察 (禁空泛形容词)
    # 仅当任一轴 <= 3 或命中 AP 时填; 高分页 None.
    top_issue: str | None = None
    suggestion: str | None = None  # actionable 修复 (引用 golden 锚点或原则编号)

    @model_validator(mode="after")
    def _ap_caps_axis(self) -> "SlideScore":
        """SKILL.md 硬约束: 命中 AP 任一, 对应轴自动 <= 2.

        命中哪一轴取决于 AP 类型 (AP1/AP2 偏 palette, AP3/AP4 偏 layout), 故此处
        只校验弱形式 '命中 AP 则至少一轴 <= 2', 抓 '命中 AP 却双轴皆高分' 的矛盾.
        """
        if self.antipatterns and min(self.layout_score, self.palette_score) > 2:
            raise ValueError(
                f"slide {self.index} 命中 {self.antipatterns} 但双轴均 > 2 "
                f"(layout={self.layout_score} palette={self.palette_score}); "
                "SKILL.md 硬约束: 命中 AP 对应轴必须 <= 2"
            )
        return self


class DeckSummary(BaseModel):
    """deck 级双轴聚合 (对应 markdown 'Deck 总分' 表)."""

    model_config = ConfigDict(extra="forbid")

    layout_avg: float = Field(ge=1, le=5)
    layout_max: int = Field(ge=1, le=5)
    layout_min: int = Field(ge=1, le=5)
    palette_avg: float = Field(ge=1, le=5)
    palette_max: int = Field(ge=1, le=5)
    palette_min: int = Field(ge=1, le=5)


class AntipatternHit(BaseModel):
    """命中反模式汇总的一条 (对应 markdown '命中反模式汇总' 表)."""

    model_config = ConfigDict(extra="forbid")

    slide: int = Field(ge=1)
    ap: str  # 反模式编号, 如 "AP4"
    description: str
    fix: str  # 修复方向


class Improvement(BaseModel):
    """deck 级改进项的一条 (对应 markdown '改进项 (按优先级)' 节)."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)  # 优先级序号 (1 = 最高)
    title: str  # 核心问题
    detail: str  # 修复方向 (引用 golden 锚点或原则编号)
    slides: list[int] = Field(default_factory=list)  # 涉及页; 全局问题留空 []


class TasteReport(BaseModel):
    """ppt:taste 一次评审的完整结构化输出 (.taste-report.json 顶层)."""

    model_config = ConfigDict(extra="forbid")

    deck: str
    timestamp: str  # ISO 8601
    pages: int = Field(ge=1)
    mode: str = Field(pattern=r"^(anchor|general-principles)$")
    anchor_library_version: str
    verdict: str  # 综合判断 2-3 句
    summary: DeckSummary
    slides: list[SlideScore]
    antipattern_hits: list[AntipatternHit] = Field(default_factory=list)
    improvements: list[Improvement] = Field(default_factory=list)

    @model_validator(mode="after")
    def _internal_consistency(self) -> "TasteReport":
        """summary / antipattern_hits / pages 必须与 slides 自洽 (LLM 产出护栏)."""
        n = len(self.slides)
        if n != self.pages:
            raise ValueError(f"pages={self.pages} 但 slides 列表长度={n}")
        if n == 0:
            raise ValueError("slides 不能为空")

        # slide index 连续 1..n 且不重复
        idxs = sorted(s.index for s in self.slides)
        if idxs != list(range(1, n + 1)):
            raise ValueError(f"slides.index 必须是连续 1..{n}, 实际 {idxs}")

        # summary avg / max / min 与 slides 实际值一致 (容差 0.01, 防 LLM 算错)
        la = sum(s.layout_score for s in self.slides) / n
        pa = sum(s.palette_score for s in self.slides) / n
        if abs(la - self.summary.layout_avg) > 0.01:
            raise ValueError(
                f"summary.layout_avg={self.summary.layout_avg} != 实际平均 {la:.4f}"
            )
        if abs(pa - self.summary.palette_avg) > 0.01:
            raise ValueError(
                f"summary.palette_avg={self.summary.palette_avg} != 实际平均 {pa:.4f}"
            )
        pairs = {
            "layout_max": (self.summary.layout_max, max(s.layout_score for s in self.slides)),
            "layout_min": (self.summary.layout_min, min(s.layout_score for s in self.slides)),
            "palette_max": (self.summary.palette_max, max(s.palette_score for s in self.slides)),
            "palette_min": (self.summary.palette_min, min(s.palette_score for s in self.slides)),
        }
        for field_name, (declared, actual) in pairs.items():
            if declared != actual:
                raise ValueError(f"summary.{field_name}={declared} != 实际 {actual}")

        # antipattern_hits 的 (slide, ap) 必须在该页 slides[].antipatterns 中声明过
        declared_aps = {s.index: set(s.antipatterns) for s in self.slides}
        for hit in self.antipattern_hits:
            if hit.ap not in declared_aps.get(hit.slide, set()):
                raise ValueError(
                    f"antipattern_hits slide={hit.slide} ap={hit.ap} "
                    f"未在该页 slides[].antipatterns 声明"
                )
        return self


def validate_taste_report_file(path: str) -> TasteReport:
    """加载并校验一份 .taste-report.json. 不合规抛 pydantic ValidationError."""
    data = json.loads(open(path, encoding="utf-8").read())
    return TasteReport.model_validate(data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="校验 .taste-report.json 是否符合 TasteReport schema"
    )
    parser.add_argument("json_path", help=".taste-report.json 路径")
    args = parser.parse_args()
    try:
        report = validate_taste_report_file(args.json_path)
    except Exception as exc:  # noqa: BLE001 — CLI 把任何校验失败转为非零退出
        print(f"FAIL: {args.json_path} 不符合 TasteReport schema\n{exc}", file=sys.stderr)
        sys.exit(1)
    print(
        f"OK: {args.json_path} 符合 TasteReport schema "
        f"({report.pages} slides, layout_avg={report.summary.layout_avg}, "
        f"palette_avg={report.summary.palette_avg})"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
