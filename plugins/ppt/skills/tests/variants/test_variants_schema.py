# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.0", "pytest>=7.0"]
# ///
"""T8：18 个 variant 子模型的正负例单元测试。

覆盖范围：
- test_variant_types_count：VARIANT_TYPES 集合大小 == 18
- test_variant_valid_and_invalid：每个 visual_type 一组 (valid, invalid) payload
- test_discriminator_mismatch：discriminator 字段（visual_type）与子模型 Literal 不匹配时 ValidationError
- test_extra_field_forbidden：extra='forbid' 对未声明字段拒绝

对应规格：SPEC-SC-V01-* ... SPEC-SC-V17-*，含 Plan T5 最终字段决策。
"""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

# Dev-2 T2 尚未交付时整个测试文件优雅 skip，不让 collection 阶段 ERROR
try:
    from schemas.variants import VariantUnion, VARIANT_TYPES  # type: ignore
except ImportError:
    VariantUnion = None  # type: ignore
    VARIANT_TYPES = None  # type: ignore

pytestmark = pytest.mark.skipif(
    VariantUnion is None,
    reason="schemas.variants 尚未交付（Dev-2 T2 前）",
)

ta = TypeAdapter(VariantUnion) if VariantUnion is not None else None


def test_variant_types_count():
    """Plan T5 决策：风险 risk-list + governance 作为独立 variant，合计 18。"""
    assert len(VARIANT_TYPES) == 18


def test_variant_types_exact_membership():
    """精确列出 18 个 visual_type，防止后续误增减。"""
    expected = {
        "cover-left-bar", "toc", "section-divider-dark",
        "kpi-stats", "matrix-2x2", "architecture-layered",
        "timeline-huawei", "process-flow-huawei",
        "swot", "roadmap", "pyramid", "heatmap-matrix", "thankyou",
        "cards-6", "rings", "personas",
        "risk-list", "governance",
    }
    assert VARIANT_TYPES == expected


# ============================================================
# Valid + Invalid payload for each variant (Plan T5 字段对齐)
# ============================================================

_MIN_MATRIX_2X2_AXIS = {"x": {"label": "难度"}, "y": {"label": "价值"}}
_MIN_MATRIX_2X2_QUADRANTS = [
    {"position": "Q1", "heading": "Q1"},
    {"position": "Q2", "heading": "Q2"},
    {"position": "Q3", "heading": "Q3"},
    {"position": "Q4", "heading": "Q4"},
]

VARIANT_CASES: list[tuple[str, dict, dict]] = [
    # (visual_type, valid_payload, invalid_payload)
    # ---- P0 八版式 ----
    ("cover-left-bar",
     {"visual_type": "cover-left-bar", "title": "封面"},
     {"visual_type": "cover-left-bar"}),                   # 缺 title
    ("toc",
     {"visual_type": "toc", "chapters": [
         {"number": "01", "title": "背景"},
         {"number": "02", "title": "方案"},
         {"number": "03", "title": "结论"},
     ]},
     {"visual_type": "toc", "chapters": [
         {"number": "01", "title": "背景"},
         {"number": "02", "title": "方案"},
     ]}),                                                   # chapters < 3 (min_length=3)
    ("section-divider-dark",
     {"visual_type": "section-divider-dark", "big_number": "01", "title": "战略"},
     {"visual_type": "section-divider-dark", "title": "战略"}),  # 缺 big_number
    ("kpi-stats",
     {"visual_type": "kpi-stats", "title": "KPI",
      "kpis": [
          {"label": "收入", "value": "1.2B"},
          {"label": "增长", "value": "42%"},
          {"label": "ROI", "value": "3.1x"},
      ]},
     {"visual_type": "kpi-stats", "title": "KPI",
      "kpis": [{"label": "A", "value": "1"}, {"label": "B", "value": "2"}]}),  # kpis < 3
    ("matrix-2x2",
     {"visual_type": "matrix-2x2", "title": "矩阵",
      "axis": _MIN_MATRIX_2X2_AXIS, "quadrants": _MIN_MATRIX_2X2_QUADRANTS},
     {"visual_type": "matrix-2x2", "title": "矩阵",
      "axis": _MIN_MATRIX_2X2_AXIS,
      "quadrants": [{"position": "Q1", "heading": "Q1"}]}),  # quadrants != 4
    ("architecture-layered",
     {"visual_type": "architecture-layered", "title": "架构",
      "layers": [
          {"header": {"code": "APP", "name": "应用层"}, "cells": [{"title": "客服"}]},
          {"header": {"code": "MOD", "name": "模型层"}, "cells": [{"title": "LLM"}]},
      ]},
     {"visual_type": "architecture-layered", "title": "架构",
      "layers": [
          {"header": {"code": "APP", "name": "应用层"}, "cells": [{"title": "客服"}]},
      ]}),                                                   # layers < 2
    ("timeline-huawei",
     {"visual_type": "timeline-huawei", "title": "时间线",
      "phases": [
          {"year": "2023", "label": "起步"},
          {"year": "2024", "label": "扩展"},
          {"year": "2025", "label": "深化"},
      ]},
     {"visual_type": "timeline-huawei", "title": "时间线",
      "phases": [{"year": "2023", "label": "起步"}, {"year": "2024", "label": "扩展"}]}),  # phases < 3
    ("process-flow-huawei",
     {"visual_type": "process-flow-huawei", "title": "流程",
      "steps": [
          {"label": "规划"}, {"label": "实施"}, {"label": "验证"},
      ]},
     {"visual_type": "process-flow-huawei", "title": "流程",
      "steps": [{"label": "规划"}, {"label": "实施"}]}),      # steps < 3

    # ---- P1 五版式 ----
    ("swot",
     {"visual_type": "swot",
      "quadrants": {
          "s": {"heading": "优势", "items": []},
          "w": {"heading": "劣势", "items": []},
          "o": {"heading": "机会", "items": []},
          "t": {"heading": "威胁", "items": []},
      }},
     {"visual_type": "swot",
      "quadrants": {
          "s": {"heading": "优势"},
          "w": {"heading": "劣势"},
          "o": {"heading": "机会"},
          # 缺 t
      }}),
    ("roadmap",
     {"visual_type": "roadmap", "title": "路线",
      "phases": [
          {"code": "P1", "title": "第一阶段"},
          {"code": "P2", "title": "第二阶段"},
          {"code": "P3", "title": "第三阶段"},
      ],
      "rows": [
          {"label": "业务", "cells": [
              {"title": "T1"}, {"title": "T2"}, {"title": "T3"},
          ]},
      ]},
     {"visual_type": "roadmap", "title": "路线",
      "phases": [{"code": "P1", "title": "第一阶段"}, {"code": "P2", "title": "第二阶段"}],
      "rows": [{"label": "业务", "cells": []}]}),            # phases < 3
    ("pyramid",
     {"visual_type": "pyramid", "title": "金字塔",
      "levels": [
          {"name": "战略"}, {"name": "战术"}, {"name": "执行"},
      ]},
     {"visual_type": "pyramid", "title": "金字塔",
      "levels": [{"name": "战略"}, {"name": "战术"}]}),        # levels < 3
    ("heatmap-matrix",
     {"visual_type": "heatmap-matrix", "title": "评估",
      "columns": ["功能", "性能", "成本"],
      "rows": [
          {"label": "方案 A", "scores": [4.0, 3.5, 2.0]},
      ]},
     {"visual_type": "heatmap-matrix", "title": "评估",
      "columns": ["功能", "性能"],                            # columns < 3 (min_length)
      "rows": [{"label": "方案 A", "scores": [4.0, 3.5]}]}),
    ("thankyou",
     {"visual_type": "thankyou"},                           # 全用默认值
     {"visual_type": "thankyou", "unknown_field": "x"}),    # extra=forbid

    # ---- P2 四版式 + variants ----
    ("cards-6",
     {"visual_type": "cards-6", "title": "六卡",
      "cards": [{"heading": f"C{i}"} for i in range(1, 7)]},
     {"visual_type": "cards-6", "title": "六卡",
      "cards": [{"heading": f"C{i}"} for i in range(1, 6)]}),  # cards != 6
    ("rings",
     {"visual_type": "rings", "title": "环",
      "rings": [
          {"label": "A"}, {"label": "B"},
      ]},
     {"visual_type": "rings", "title": "环",
      "rings": [{"label": "A"}]}),                          # rings < 2
    ("personas",
     {"visual_type": "personas", "title": "角色",
      "personas": [
          {"role": "CEO", "name": "张三"},
          {"role": "CTO", "name": "李四"},
      ]},
     {"visual_type": "personas", "title": "角色",
      "personas": [{"role": "CEO", "name": "张三"}]}),       # personas < 2
    ("risk-list",
     {"visual_type": "risk-list", "title": "风险",
      "risks": [
          {"number": "01", "title": "R1", "desc": "D1", "severity": "HIGH"},
          {"number": "02", "title": "R2", "desc": "D2", "severity": "MED"},
      ]},
     {"visual_type": "risk-list", "title": "风险",
      "risks": [
          {"number": "01", "title": "R1", "desc": "D1", "severity": "UNKNOWN"},  # Literal 外
      ]}),
    ("governance",
     {"visual_type": "governance", "title": "治理",
      "top": {"name": "决策委员会"},
      "units": [
          {"code": "S", "name": "战略", "items": ["愿景"]},
          {"code": "T", "name": "技术", "items": ["架构"]},
      ]},
     {"visual_type": "governance", "title": "治理",
      "top": {"name": "决策委员会"},
      "units": [{"code": "S", "name": "战略", "items": ["愿景"]}]}),  # units < 2
]


@pytest.mark.parametrize("vt,valid_data,invalid_data", VARIANT_CASES, ids=[c[0] for c in VARIANT_CASES])
def test_variant_valid_and_invalid(vt: str, valid_data: dict, invalid_data: dict):
    """每个 variant 的正/负例。

    - valid_data 必须通过 TypeAdapter 校验
    - invalid_data 必须抛 ValidationError
    """
    result = ta.validate_python(valid_data)
    assert getattr(result, "visual_type", None) == vt

    with pytest.raises(ValidationError):
        ta.validate_python(invalid_data)


def test_cases_cover_all_variants():
    """保证 VARIANT_CASES 覆盖全部 VARIANT_TYPES（防止漏测新增的 variant）。"""
    covered = {c[0] for c in VARIANT_CASES}
    missing = VARIANT_TYPES - covered
    assert not missing, f"VARIANT_CASES 缺少下列 variant 的用例: {sorted(missing)}"


# ============================================================
# 额外断言（discriminator / extra=forbid）
# ============================================================

def test_discriminator_visual_type_mismatch():
    """discriminator 值不在任何子模型 Literal 中 → 拒绝。"""
    with pytest.raises(ValidationError) as excinfo:
        ta.validate_python({"visual_type": "not-a-variant", "title": "X"})
    assert "visual_type" in str(excinfo.value).lower() or "discriminator" in str(excinfo.value).lower()


def test_extra_field_forbidden_example():
    """extra='forbid'：未声明的字段必须被拒绝。Plan T5 为所有子模型加了 extra='forbid'。"""
    with pytest.raises(ValidationError):
        ta.validate_python({
            "visual_type": "cover-left-bar",
            "title": "合法标题",
            "unknown_extra_field": "not allowed",
        })


def test_kpi_trend_enum_only_accepts_3_values():
    """O2 决策（Architect 覆写版）：`trend: Literal['up','down','flat'] | None`，
    加 enum 约束；自由文本走独立字段 `trend_text`。

    正例：'up'/'down'/'flat'/None/省略 全通过；负例：任意其他字符串被拒。
    """
    # 正例
    ok_payload = {
        "visual_type": "kpi-stats", "title": "KPI",
        "kpis": [
            {"label": "A", "value": "1", "trend": "up"},
            {"label": "B", "value": "2", "trend": "down", "trend_text": "YoY -5%"},
            {"label": "C", "value": "3", "trend": "flat"},
            {"label": "D", "value": "4", "trend": None},
            {"label": "E", "value": "5"},  # 省略 trend
        ],
    }
    ta.validate_python(ok_payload)

    # 负例：任意非枚举值必须被拒
    bad_payload = {
        "visual_type": "kpi-stats", "title": "KPI",
        "kpis": [
            {"label": "A", "value": "1", "trend": "up"},
            {"label": "B", "value": "2", "trend": "custom-trend-xyz"},  # 非法
            {"label": "C", "value": "3"},
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        ta.validate_python(bad_payload)
    # 错误信息应指向 trend 字段
    assert "trend" in str(excinfo.value).lower()


def test_heatmap_scores_0_to_5_range():
    """O3 决策（Architect 覆写版）：`scores: list[Annotated[float, Field(ge=0, le=5)]]`，
    加值域约束 0..5。

    正例：0 / 0.5 / 2.5 / 4.5 / 5 均通过；负例：-99 和 1e9 必须被拒。
    """
    # 正例
    ok_payload = {
        "visual_type": "heatmap-matrix", "title": "评估",
        "columns": ["A", "B", "C"],
        "rows": [
            {"label": "方案 X", "scores": [0.0, 2.5, 4.5]},
            {"label": "方案 Y", "scores": [0.5, 3.0, 5.0]},
        ],
    }
    ta.validate_python(ok_payload)

    # 负例：下越界 -99
    neg_low = {
        "visual_type": "heatmap-matrix", "title": "评估",
        "columns": ["A", "B", "C"],
        "rows": [{"label": "方案 X", "scores": [-99.0, 0.0, 3.0]}],
    }
    with pytest.raises(ValidationError):
        ta.validate_python(neg_low)

    # 负例：上越界 1e9
    neg_high = {
        "visual_type": "heatmap-matrix", "title": "评估",
        "columns": ["A", "B", "C"],
        "rows": [{"label": "方案 X", "scores": [0.0, 3.0, 1e9]}],
    }
    with pytest.raises(ValidationError):
        ta.validate_python(neg_high)


def test_matrix_2x2_quadrant_positions_are_literal():
    """Plan T5：QuadrantItem.position 必须是 Literal['Q1','Q2','Q3','Q4']。"""
    bad_payload = {
        "visual_type": "matrix-2x2", "title": "矩阵",
        "axis": _MIN_MATRIX_2X2_AXIS,
        "quadrants": [
            {"position": "TopLeft", "heading": "Q1"},  # 非 Literal 值
            {"position": "Q2", "heading": "Q2"},
            {"position": "Q3", "heading": "Q3"},
            {"position": "Q4", "heading": "Q4"},
        ],
    }
    with pytest.raises(ValidationError):
        ta.validate_python(bad_payload)


def test_architecture_cells_bounded():
    """Plan T5：ArchLayer.cells: Field(min_length=1, max_length=6)。"""
    over_cells = [{"title": f"c{i}"} for i in range(1, 8)]  # 7 > 6
    bad_payload = {
        "visual_type": "architecture-layered", "title": "架构",
        "layers": [
            {"header": {"code": "A", "name": "A"}, "cells": over_cells},
            {"header": {"code": "B", "name": "B"}, "cells": [{"title": "b1"}]},
        ],
    }
    with pytest.raises(ValidationError):
        ta.validate_python(bad_payload)
