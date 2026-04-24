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
    """
    heading: str | None = None      # 卡片/列/阶段标题
    body: str                       # 主体文本
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
    """单页内容。"""
    model_config = ConfigDict(extra="allow")
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
    """单页设计参数。"""
    model_config = ConfigDict(extra="allow")
    background: str = "#FFFFFF"
    layout_variant: str | None = None
    title_color: str = "#1A1A2E"
    title_size_pt: int = 28
    body_color: str = "#4A4A68"
    body_size_pt: int = 16
    accent_color: str = "#2563EB"
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

VALID_VISUAL_TYPES: set[str] = _LEGACY_VISUAL_TYPES | VARIANT_TYPES


class SlideSpec(BaseModel):
    """单页 slide 完整规格。

    华为 18 个新版式的专属字段通过 `variant` 字段承载（Annotated discriminated union，
    extra='forbid' 严格校验）。renderer 从 `spec.variant` 读取结构化数据。

    兼容模式：不填 `variant` 的旧生产者可把字段直接放进 content 顶层
    （SlideContent.extra='allow' 兜底），validate_plan.py 优先校验 `slide['variant']`，
    缺失时退回从 content 取字段子集按 visual_type 对应子模型二次校验。
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
