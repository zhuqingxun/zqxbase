# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.0", "pyyaml>=6.0"]
# ///
"""Pydantic V2 schema for slide-plan.yaml.

Core data contract between plan.py (producer) and render.py (consumer).
Same YAML input always produces same PPTX output.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.variants import VARIANT_TYPES, VariantUnion


class SlideRole(str, Enum):
    """Slide 在叙事中的角色。"""
    TITLE = "title"
    SECTION = "section"
    CONTENT = "content"
    DATA = "data"
    CLOSING = "closing"
    APPENDIX = "appendix"


class PlanMeta(BaseModel):
    """Slide plan 元数据。"""
    title: str
    source_files: list[str] = []
    preset: str = "research-report"
    theme: str = "huawei"
    target_audience: str = ""
    generated_at: datetime = Field(default_factory=datetime.now)


class Narrative(BaseModel):
    """叙事结构。"""
    thesis: str
    arc: str
    total_slides: int = Field(ge=1)


class StructuredPoint(BaseModel):
    """结构化内容要点——支持卡片标题、指标值等分层信息。

    向后兼容：key_points 接受 str | StructuredPoint 混合列表。
    2026-05-19 audit fix: body 默认 "" (原 required), 避免 LLM 输出 `{heading: "x"}` 缺 body
    时 Union[str, StructuredPoint] fallback 失败 plan 校验 abort.
    """
    heading: str | None = None      # 卡片/列/阶段标题
    body: str = ""                  # 主体文本 (默认空允许 dict 缺 body, renderer 容错)
    metric_value: str | None = None # 大号指标值（如 "40%", "1:0.84"）
    metric_label: str | None = None # 指标标签（如 "效率提升"）


class TableData(BaseModel):
    """表格数据。"""
    model_config = ConfigDict(extra="allow")
    headers: list[str] = []
    rows: list[list[str]] = []


class ChartSpec(BaseModel):
    """图表规格。"""
    model_config = ConfigDict(extra="allow")
    chart_type: str = "bar"
    data: dict[str, Any] = {}
    labels: list[str] = []


class ImagePosition(BaseModel):
    """图片位置(英寸)。"""
    x: float = 0.0
    y: float = 0.0
    width: float = 6.0
    height: float = 4.0


class SlideContent(BaseModel):
    """单页内容。

    2026-06-19 ARCH-002 阶段2 (T12): extra='allow'→'forbid'。收紧数据契约——
    华为版式专属字段必须放 slide.variant (path X) 下, 禁止平铺到 content 顶层
    (path Y)。path Y 平铺数据经 SlidePlan.from_yaml 构造时直接 ValidationError。
    """
    model_config = ConfigDict(extra="forbid")
    title: str
    subtitle: str | None = None
    description: str | None = None
    key_points: list[str | StructuredPoint] | None = None
    body_text: str | None = None
    footnote: str | None = None
    table_data: TableData | None = None
    image_ref: str | None = None
    chart_spec: ChartSpec | None = None


class SlideDesign(BaseModel):
    """单页设计参数。

    所有颜色字段默认 None, 表示使用主题 token。renderer 拿到 None 时
    fallback 到 theme.colors.{ink/ink_soft/primary} 等 huawei token。
    历史默认蓝色码 (品牌蓝 / 深蓝灰 / 灰蓝) 在 huawei 主题下视觉错位, 已废弃。
    """
    model_config = ConfigDict(extra="allow")
    background: str = "#FFFFFF"
    layout_variant: str | None = None
    title_color: str | None = None
    title_size_pt: int = 28
    body_color: str | None = None
    body_size_pt: int = 16
    accent_color: str | None = None
    font_family: str = "Microsoft YaHei"
    card_colors: list[str] | None = None
    image_position: ImagePosition | None = None


_LEGACY_VISUAL_TYPES: set[str] = {
    "hero-statement", "quote-hero", "bullets",
    "cards-2", "cards-3", "cards-4", "cards-5",
    "comparison-2", "comparison-3", "comparison-4", "comparison-5",
    "process-2-phase", "process-3-phase", "process-4-phase", "process-5-phase",
    "data-contrast", "table", "comparison-tables",
    "timeline-horizontal", "story-card",
    "framework", "framework-2col", "framework-3col", "framework-4col",
}

# 2026-06-19 S4 收敛 (T13): 废弃但**仍合法可渲染**的 visual_type (向后兼容一版)。
# 这些类型停止被 prompt_assembler / SKILL.md 推荐 (Architect 侧改动), schema 侧仅
# 标记 deprecated —— 它们仍在 _LEGACY_VISUAL_TYPES 内 (故 VALID_VISUAL_TYPES 不变,
# 旧 plan 仍能渲染), renderer 也保留一版 (Dev-1 侧不物理删)。下一版本评估物理删除。
# framework 系列被无后缀自适应母版 (cards/process/comparison) + huawei 18 版式取代;
# story-card / timeline-horizontal 被 quote-hero / timeline-huawei 取代。
_DEPRECATED_VISUAL_TYPES: set[str] = {
    "framework", "framework-2col", "framework-3col", "framework-4col",
    "story-card",
    "timeline-horizontal",
}

VALID_VISUAL_TYPES: set[str] = _LEGACY_VISUAL_TYPES | VARIANT_TYPES


class SlideSpec(BaseModel):
    """单页 slide 完整规格。

    华为 18 个新版式的专属字段通过 `variant` 字段承载（Annotated discriminated union，
    extra='forbid' 严格校验）。renderer 从 `spec.variant` 读取结构化数据。

    数据契约（2026-06-19 ARCH-002 阶段2 收紧后）：专属字段必须放 `slide.variant`
    下（path X）。SlideContent 已改 extra='forbid'，**不再**接受字段平铺到 content
    顶层（path Y）——validate_plan.py 对缺 variant 块的平铺数据直接判 FAIL。
    """

    id: int = Field(ge=1)
    role: SlideRole
    chapter: str | None = None
    content: SlideContent
    visual_type: str = "bullets"
    design: SlideDesign = Field(default_factory=SlideDesign)
    variant: VariantUnion | None = None

    @field_validator("visual_type")
    @classmethod
    def validate_visual_type(cls, v: str) -> str:
        if v not in VALID_VISUAL_TYPES:
            raise ValueError(
                f"Unknown visual_type: {v}. Valid: {sorted(VALID_VISUAL_TYPES)}"
            )
        return v


class SlidePlan(BaseModel):
    """slide-plan.yaml 顶层 schema。"""
    meta: PlanMeta
    narrative: Narrative
    slides: list[SlideSpec]

    # Phase 2/3 预留
    sync_manifest: Any = None
    edit_operations: Any = None
    merge_sources: Any = None

    def to_yaml(self, path: str) -> None:
        """序列化为 YAML 文件。"""
        data = self.model_dump(mode="json")
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, path: str) -> "SlidePlan":
        """从 YAML 文件反序列化。"""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)
