# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""review.py: Review Agent framework utilities.

Provides:
- Structured review JSON parsing (with error tolerance)
- Score calculation
- Stagnation detection for degradation protection
- Review history tracking

This module is used by SKILL.md prompts. The actual review logic
runs in Claude (the AI plays the reviewer role), this module
provides helper functions for the Python-side iteration control.
"""

import json
import re
from dataclasses import dataclass, field


@dataclass
class ReviewResult:
    """Parsed review result."""
    passed: bool
    score: float
    dimensions: dict[str, dict]  # {name: {score, evidence, issues}}
    threshold: float
    improvement_directives: list[str]
    raw_json: str = ""


@dataclass
class ReviewHistory:
    """Track review iterations for stagnation detection."""
    rounds: list[ReviewResult] = field(default_factory=list)
    best_score: float = 0.0
    best_round: int = 0
    stagnation_count: int = 0

    def add_round(self, result: ReviewResult) -> None:
        self.rounds.append(result)
        if result.score > self.best_score:
            self.best_score = result.score
            self.best_round = len(self.rounds)
            self.stagnation_count = 0
        else:
            self.stagnation_count += 1

    @property
    def should_escalate(self) -> bool:
        """连续 3 轮无提升 -> 升级给用户。"""
        return self.stagnation_count >= 3

    @property
    def max_rounds_reached(self) -> bool:
        """第 10 轮强制输出。"""
        return len(self.rounds) >= 10


def parse_review_json(text: str) -> ReviewResult:
    """Parse review JSON from AI output with error tolerance.

    Handles: markdown code fences, extra text before/after JSON,
    partial JSON, missing fields.
    """
    # 1. Try to extract JSON from markdown code fence
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1)
    else:
        # 2. Try to find raw JSON object
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            json_str = brace_match.group(0)
        else:
            # 3. Fallback: treat as failed review
            return ReviewResult(
                passed=False, score=0.0, dimensions={},
                threshold=4.0, improvement_directives=["无法解析审查 JSON"],
                raw_json=text,
            )

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return ReviewResult(
            passed=False, score=0.0, dimensions={},
            threshold=4.0, improvement_directives=["JSON 格式错误"],
            raw_json=json_str,
        )

    # Calculate average score from dimensions
    dims = data.get("dimensions", {})
    scores = [d.get("score", 0) for d in dims.values() if isinstance(d, dict)]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return ReviewResult(
        passed=data.get("pass", False),
        score=avg_score,
        dimensions=dims,
        threshold=data.get("threshold", 4.0),
        improvement_directives=data.get("improvement_directives", []),
        raw_json=json_str,
    )


# Stage-specific review configurations
REVIEW_CONFIGS = {
    "parse": {
        "threshold": 4.5,
        "max_rounds": 10,
        "dimensions": ["completeness", "structure_accuracy", "format_fidelity"],
    },
    "architect": {
        "threshold": 4.0,
        "max_rounds": 10,
        "dimensions": [
            "narrative_coherence", "information_coverage",
            "audience_match", "conciseness", "structural_balance",
        ],
    },
    "plan": {
        "threshold": 4.0,
        "max_rounds": 10,
        "dimensions": [
            "visual_type_fitness", "design_consistency",
            "theme_compliance", "information_hierarchy",
        ],
    },
    "render": {
        "threshold": 4.5,
        "max_rounds": 10,
        "dimensions": [
            "no_overflow", "font_coverage",
            "image_ratio", "visual_consistency", "readability",
        ],
    },
}
