"""validators 共享数据结构 (S4 Phase 2 从 validate_plan.py 拆出)。纯 dataclass, 无依赖。"""
from __future__ import annotations

from dataclasses import dataclass, field


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

