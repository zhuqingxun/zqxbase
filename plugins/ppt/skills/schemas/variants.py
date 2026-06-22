# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.0"]
# ///
"""华为主题 18 个 visual_type 的 Pydantic Content 子模型 + VariantUnion。

按 PRD §7.2 与 Plan §T5 实现，通过 `Annotated[Union[...], Field(discriminator='visual_type')]`
挂到 `SlideSpec.variant` 字段实现 discriminated union。

所有 Content 子模型开头携带 `visual_type: Literal['<name>']` 作为 discriminator，
并设置 `model_config = ConfigDict(extra='forbid')` 以严格校验未知字段。

子模型清单（18 个）：
- P0 八个: cover-left-bar / toc / section-divider-dark / kpi-stats / matrix-2x2
          architecture-layered / timeline-huawei / process-flow-huawei
- P1 五个: swot / roadmap / pyramid / heatmap-matrix / thankyou
- P2 三个: cards-6 / rings / personas
- 变体两个: risk-list / governance

2026-06-18 S4 Phase 3 (T7) 收敛: 新增 3 个无后缀自适应母版 Content 模型
（cards / process / comparison）。它们用 `Literal[无后缀, 老后缀...]` 多值
discriminator 复用同一模型——无后缀值置首位, 使 prompt_assembler 自动反射出
无后缀母版名 (`_visual_type_of` 取 Literal 首值); 老后缀 (cards-2..5 /
process-2..5-phase / comparison-2..5) 保留为 deprecated alias 走同一模型,
向后兼容现有 slide-plan.yaml (蓝图 §3.2/§3.3 钦定)。布局由 `len(points)` 派生
(renderer 层 `n = clamp(len(get_points), lo, hi)`, 蓝图 §3.1), 故字段为自适应
区间的 `points` 列表而非固定 N。cards-6 (Cards6Content) 保持不动 (typed 产物
+ 测试依赖, 不并入自适应模型)。
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ==================== 嵌套类型 ====================


class MetaItem(BaseModel):
    """封面 meta 栏条目（如"出品方: xxx"）。"""

    model_config = ConfigDict(extra="forbid")
    label: str
    value: str


class TocChapter(BaseModel):
    """目录章节条目。"""

    model_config = ConfigDict(extra="forbid")
    number: str
    title: str
    page: str | None = None
    active: bool = False


class Kpi(BaseModel):
    """KPI 统计面板单项。"""

    model_config = ConfigDict(extra="forbid")
    label: str
    value: str
    unit: str | None = None
    desc: str | None = None
    trend: Literal["up", "down", "flat"] | None = None
    trend_text: str | None = None  # 自由文本，如 "YoY +12%"


class Axis(BaseModel):
    """矩阵轴定义。"""

    model_config = ConfigDict(extra="forbid")
    label: str
    low: str = "低"
    high: str = "高"


class MatrixAxis(BaseModel):
    """2x2 矩阵双轴。"""

    model_config = ConfigDict(extra="forbid")
    x: Axis
    y: Axis


class QuadrantItem(BaseModel):
    """2x2 矩阵象限内容。"""

    model_config = ConfigDict(extra="forbid")
    position: Literal["Q1", "Q2", "Q3", "Q4"]
    heading: str
    desc: str | None = None
    tags: list[str] = []
    highlight: bool = False


class ArchHeader(BaseModel):
    """架构层 header 标签（如"L1 接入层"）。"""

    model_config = ConfigDict(extra="forbid")
    code: str
    name: str


class ArchCell(BaseModel):
    """架构层单 cell。"""

    model_config = ConfigDict(extra="forbid")
    title: str
    desc: str | None = None
    highlight: bool = False


class ArchLayer(BaseModel):
    """架构层（含 header + 1..6 cells）。"""

    model_config = ConfigDict(extra="forbid")
    header: ArchHeader
    cells: list[ArchCell] = Field(min_length=1, max_length=6)
    highlight: bool = False


class TimelinePhase(BaseModel):
    """华为风格时间线单阶段。"""

    model_config = ConfigDict(extra="forbid")
    year: str
    label: str
    items: list[str] = []


class ProcessStep(BaseModel):
    """流程图单步骤。"""

    model_config = ConfigDict(extra="forbid")
    label: str
    desc: str | None = None


class SwotQuadrant(BaseModel):
    """SWOT 单象限。"""

    model_config = ConfigDict(extra="forbid")
    heading: str
    items: list[str] = Field(default_factory=list)


class SwotQuadrants(BaseModel):
    """SWOT 四象限容器。"""

    model_config = ConfigDict(extra="forbid")
    s: SwotQuadrant
    w: SwotQuadrant
    o: SwotQuadrant
    t: SwotQuadrant


class RoadmapPhase(BaseModel):
    """路线图列（阶段）。"""

    model_config = ConfigDict(extra="forbid")
    code: str
    title: str
    summary: str | None = None


class RoadmapCell(BaseModel):
    """路线图单元格。"""

    model_config = ConfigDict(extra="forbid")
    title: str
    desc: str | None = None
    emphasis: Literal["bar", "bar2"] | None = None


class RoadmapRow(BaseModel):
    """路线图行（泳道）。"""

    model_config = ConfigDict(extra="forbid")
    label: str
    cells: list[RoadmapCell]


class Milestone(BaseModel):
    """路线图里程碑。"""

    model_config = ConfigDict(extra="forbid")
    code: str
    title: str
    desc: str | None = None


class PyramidLevel(BaseModel):
    """金字塔层级。"""

    model_config = ConfigDict(extra="forbid")
    name: str
    tag: str | None = None


class PyramidDescription(BaseModel):
    """金字塔侧栏描述。"""

    model_config = ConfigDict(extra="forbid")
    number: str
    heading: str
    body: str | None = None


class HeatmapRow(BaseModel):
    """热力矩阵单行；scores 取值 0..5（支持 0.5 档精度）。"""

    model_config = ConfigDict(extra="forbid")
    label: str
    scores: list[Annotated[float, Field(ge=0, le=5)]]
    total: float | None = None


class Contact(BaseModel):
    """致谢页联系人。"""

    model_config = ConfigDict(extra="forbid")
    label: str
    value: str

    @model_validator(mode="after")
    def _check_at_least_one_non_empty(self) -> "Contact":
        """label / value 至少一个有实际内容 (非纯空白)。

        两者皆空 (含纯空白) 时, 致谢页 renderer (engine/renderers/huawei/thankyou.py)
        仍无条件 `cy += 0.78` 推进光标, 渲染出占 0.78" 垂直位却无任何文字的幽灵间隙。
        """
        if not (self.label.strip() or self.value.strip()):
            raise ValueError("Contact 的 label 与 value 不能同时为空 (至少一个需非空白)")
        return self


class Card(BaseModel):
    """六宫格卡片。"""

    model_config = ConfigDict(extra="forbid")
    heading: str
    body: str | None = None
    icon: str | None = None


class AdaptivePoint(BaseModel):
    """自适应母版（cards / process / comparison）的单个条目。

    与 schemas.slide_plan.StructuredPoint 同构（heading + body），是无后缀母版
    path X 的结构化承载。renderer 层 `get_points(spec)` 既读 content.key_points
    (path Y), 也能从此处构造 points——双路兼容 (renderer_kit._render_cards 先例)。
    """

    model_config = ConfigDict(extra="forbid")
    heading: str | None = None
    body: str | None = None
    icon: str | None = None  # cards 场景可选图标; process/comparison 忽略


class Ring(BaseModel):
    """同心环（rings 版式）。"""

    model_config = ConfigDict(extra="forbid")
    label: str
    sublabel: str | None = None
    style: Literal["outline", "solid"] = "outline"


class RingStep(BaseModel):
    """rings 版式右侧编号列表项。"""

    model_config = ConfigDict(extra="forbid")
    number: str
    heading: str
    body: str | None = None


class Persona(BaseModel):
    """角色卡（personas 版式）。"""

    model_config = ConfigDict(extra="forbid")
    role: str
    name: str
    # 2026-05-19 audit fix: 加 max_length=6 防 LLM 输出 10+ attrs 让 renderer 静默截断 quote 区
    # (renderers_huawei.py:1864-1925 persona quote_h 累积 cy 超 area 时计算结果为负, if 0.4 < neg 永假, 跳过 quote 绘制).
    attrs: list[MetaItem] = Field(default_factory=list, max_length=6)
    quote: str | None = None
    citation: str | None = None


class RiskItem(BaseModel):
    """风险清单单项。"""

    model_config = ConfigDict(extra="forbid")
    number: str
    title: str
    desc: str
    mitigation: str | None = None
    severity: Literal["HIGH", "MED", "LOW"]
    impact: str | None = None
    probability: str | None = None


class GovTop(BaseModel):
    """治理架构顶部主体。"""

    model_config = ConfigDict(extra="forbid")
    name: str
    tag: str | None = None


class GovUnit(BaseModel):
    """治理架构下级单元。"""

    model_config = ConfigDict(extra="forbid")
    code: str
    name: str
    items: list[str]


class RaciTable(BaseModel):
    """RACI 责任矩阵（可选）。"""

    model_config = ConfigDict(extra="forbid")
    columns: list[str]
    rows: list[list[str]]


# ==================== 18 个 Content 子模型 ====================


class CoverLeftBarContent(BaseModel):
    """封面：左侧 16px 红条 + 108px 大标题。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["cover-left-bar"]
    eyebrow: str | None = None
    title: str
    emphasis: str | None = None
    subtitle: str | None = None
    meta: list[MetaItem] = []


class TocContent(BaseModel):
    """目录页：3..8 章节编号列表。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["toc"]
    title: str = "目录"
    chapters: list[TocChapter] = Field(min_length=3, max_length=8)


class SectionDividerDarkContent(BaseModel):
    """章节分隔：深色底 + 360px 大数字。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["section-divider-dark"]
    big_number: str
    eyebrow: str | None = None
    title: str
    description: str | None = None


class KpiStatsContent(BaseModel):
    """KPI 统计面板：3..6 个大号指标。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["kpi-stats"]
    title: str
    subtitle: str | None = None
    kpis: list[Kpi] = Field(min_length=3, max_length=6)


class Matrix2x2Content(BaseModel):
    """2x2 矩阵：双轴 + 四象限。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["matrix-2x2"]
    title: str
    subtitle: str | None = None
    axis: MatrixAxis
    quadrants: list[QuadrantItem] = Field(min_length=4, max_length=4)


class ArchitectureLayeredContent(BaseModel):
    """分层架构：2..6 层，每层 1..6 cell。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["architecture-layered"]
    title: str
    subtitle: str | None = None
    layers: list[ArchLayer] = Field(min_length=2, max_length=6)
    base_note: str | None = None


class TimelineHuaweiContent(BaseModel):
    """华为风格时间线：3..6 阶段。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["timeline-huawei"]
    title: str
    subtitle: str | None = None
    phases: list[TimelinePhase] = Field(min_length=3, max_length=6)


class ProcessFlowHuaweiContent(BaseModel):
    """流程图：3..6 步骤，箭头串联。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["process-flow-huawei"]
    title: str
    subtitle: str | None = None
    steps: list[ProcessStep] = Field(min_length=3, max_length=6)


class SwotContent(BaseModel):
    """SWOT 四象限。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["swot"]
    title: str = "SWOT 分析"
    quadrants: SwotQuadrants


class RoadmapContent(BaseModel):
    """路线图：3..5 阶段列 x 1..5 泳道行。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["roadmap"]
    title: str
    subtitle: str | None = None
    phases: list[RoadmapPhase] = Field(min_length=3, max_length=5)
    rows: list[RoadmapRow] = Field(min_length=1, max_length=5)
    milestones: list[Milestone] = []


class PyramidContent(BaseModel):
    """金字塔：3..5 层 + 侧栏描述。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["pyramid"]
    title: str
    subtitle: str | None = None
    levels: list[PyramidLevel] = Field(min_length=3, max_length=5)
    descriptions: list[PyramidDescription] = []


class HeatmapMatrixContent(BaseModel):
    """热力矩阵：3..6 列 x N 行，score 0..5。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["heatmap-matrix"]
    title: str
    subtitle: str | None = None
    columns: list[str] = Field(min_length=3, max_length=6)
    total_column_label: str | None = None
    # 2026-05-19 audit fix: 加 max_length=12 防 N > 12 时 table 总高度被 area_h clamp + word_wrap=False
    # 让文字超出 cell 边界 (renderers_huawei.py:1547-1551).
    rows: list[HeatmapRow] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def _check_row_scores_length(self) -> "HeatmapMatrixContent":
        for i, row in enumerate(self.rows):
            if len(row.scores) != len(self.columns):
                raise ValueError(
                    f"rows[{i}].scores length {len(row.scores)} != columns length {len(self.columns)}"
                )
        return self


class ThankyouContent(BaseModel):
    """致谢页：360px "Thank you" + 联系方式栏。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["thankyou"]
    eyebrow: str | None = None
    title: str = "Thank"
    emphasis: str = "you"
    subtitle: str | None = None
    contacts: list[Contact] = []


class Cards6Content(BaseModel):
    """六宫格卡片（3 列 x 2 行）。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["cards-6"]
    title: str
    subtitle: str | None = None
    cards: list[Card] = Field(min_length=6, max_length=6)


class RingsContent(BaseModel):
    """同心环：2..4 环 + 右侧编号列表。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["rings"]
    title: str
    subtitle: str | None = None
    rings: list[Ring] = Field(min_length=2, max_length=4)
    steps: list[RingStep] = []


class PersonasContent(BaseModel):
    """角色卡：2..4 个 persona。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["personas"]
    title: str
    subtitle: str | None = None
    personas: list[Persona] = Field(min_length=2, max_length=4)


class RiskListContent(BaseModel):
    """风险清单：2..6 风险项，含严重度。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["risk-list"]
    title: str
    subtitle: str | None = None
    risks: list[RiskItem] = Field(min_length=2, max_length=6)


class GovernanceContent(BaseModel):
    """治理架构：顶部主体 + 2..4 下级单元 + 可选 RACI。"""

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["governance"]
    title: str
    subtitle: str | None = None
    top: GovTop
    units: list[GovUnit] = Field(min_length=2, max_length=4)
    raci: RaciTable | None = None


# ==================== 自适应母版（无后缀，T7 收敛新增）====================


class CardsContent(BaseModel):
    """自适应卡片母版：2..6 张卡，布局由 len(points) 派生。

    收敛 legacy cards-2..5 (单行) + huawei cards-6 (3x2 网格) 为单一母版:
    n∈{2,3} 单行 / n=4 双行 2x2 / n∈{5,6} 3x2 网格 (复用 cards-6 网格底座)。
    无后缀 `cards` 为首选; cards-2..5 为 deprecated alias (走同模型, 向后兼容)。
    cards-6 仍由独立 Cards6Content 承载 (不并入), 此处不含 cards-6 alias。
    """

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal["cards", "cards-2", "cards-3", "cards-4", "cards-5"]
    title: str
    subtitle: str | None = None
    points: list[AdaptivePoint] = Field(min_length=2, max_length=6)


class ProcessContent(BaseModel):
    """自适应流程母版：2..5 步，箭头串联，布局由 len(points) 派生。

    收敛 legacy process-2..5-phase 为单一母版 (复用 process-flow-huawei 底座)。
    无后缀 `process` 为首选; process-2..5-phase 为 deprecated alias。
    huawei `process-flow-huawei` (ProcessFlowHuaweiContent) 保持独立, 不并入。
    """

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal[
        "process", "process-2-phase", "process-3-phase",
        "process-4-phase", "process-5-phase",
    ]
    title: str
    subtitle: str | None = None
    points: list[AdaptivePoint] = Field(min_length=2, max_length=5)


class ComparisonContent(BaseModel):
    """自适应对比母版：2..5 列，含 header row，列数由 len(points) 派生。

    收敛 legacy comparison-2..5 为单一母版 (保留 N 列对比语义, 不并 adaptive-cards)。
    无后缀 `comparison` 为首选; comparison-2..5 为 deprecated alias。
    """

    model_config = ConfigDict(extra="forbid")
    visual_type: Literal[
        "comparison", "comparison-2", "comparison-3",
        "comparison-4", "comparison-5",
    ]
    title: str
    subtitle: str | None = None
    points: list[AdaptivePoint] = Field(min_length=2, max_length=5)


# ==================== Discriminated Union ====================


VariantUnion = Annotated[
    Union[
        CoverLeftBarContent,
        TocContent,
        SectionDividerDarkContent,
        KpiStatsContent,
        Matrix2x2Content,
        ArchitectureLayeredContent,
        TimelineHuaweiContent,
        ProcessFlowHuaweiContent,
        SwotContent,
        RoadmapContent,
        PyramidContent,
        HeatmapMatrixContent,
        ThankyouContent,
        Cards6Content,
        RingsContent,
        PersonasContent,
        RiskListContent,
        GovernanceContent,
        # T7 收敛: 无后缀自适应母版 (多值 Literal discriminator, 含 deprecated alias)
        CardsContent,
        ProcessContent,
        ComparisonContent,
    ],
    Field(discriminator="visual_type"),
]


# typed variant 母版的 visual_type 字面量集合（供 slide_plan.py 扩充 valid_types
# + validate_plan/prompt_assembler 单源）。
# 18 huawei 母版 + 3 无后缀自适应母版 (cards/process/comparison, T7 收敛新增) = 21。
# 老后缀 alias (cards-2..5 / process-2..5-phase / comparison-2..5) **不**列入此集——
# 它们仍在 schemas.slide_plan._LEGACY_VISUAL_TYPES 中保证 visual_type 合法性,
# 应用率口径归类 (legacy vs 母版) 留 T11 处理。无后缀 3 值是 LLM 应选的母版名。
VARIANT_TYPES: set[str] = {
    "cover-left-bar",
    "toc",
    "section-divider-dark",
    "kpi-stats",
    "matrix-2x2",
    "architecture-layered",
    "timeline-huawei",
    "process-flow-huawei",
    "swot",
    "roadmap",
    "pyramid",
    "heatmap-matrix",
    "thankyou",
    "cards-6",
    "rings",
    "personas",
    "risk-list",
    "governance",
    # T7 收敛: 无后缀自适应母版
    "cards",
    "process",
    "comparison",
}
