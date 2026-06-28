# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""architect.py: Stage 2 utilities - content architecture helpers.

Provides:
- Load parsed-content.json
- Load preset YAML
- Save content-architecture.yaml
- Validate architecture against preset rules

The actual architecture design is done by AI (Claude) in the SKILL.md prompt.
This script provides helper functions for data I/O.

Usage:
    # Load parsed content and preset
    uv run --script engine/architect.py load <parsed-content.json> --preset <preset-name>

    # Validate architecture
    uv run --script engine/architect.py validate <content-architecture.yaml> --preset <preset-name>
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parent.parent
PRESETS_DIR = SKILLS_DIR / "presets"

# 防 path traversal: preset/theme name 必须是简单标识符
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# 结构性章节关键词 (封面/目录/致谢类): 标题天然是短词, 豁免 action_title 长度检查,
# 且不计入"内容章节"(role 覆盖判定). 见 issue-ppt-validate-architecture-overstrict.
_STRUCTURAL_TITLE_KEYWORDS = (
    "封面", "目录", "致谢", "感谢", "谢谢", "结束语", "结语", "后记",
    "thank", "cover", "contents", "agenda", "toc",
)

# 内容章节标题最小长度: 真实华为风格内容章节标题为 9-15 字主题短语 (非 10+ 字完整句),
# 故仅拦截退化标题 (空 / 单双字占位), 不再强制 action_title 的 >=10 字完整句启发式.
_MIN_CONTENT_CHAPTER_TITLE = 4


def _is_structural_chapter(chapter: dict) -> bool:
    """判定章节是否为结构性章节 (封面/目录/致谢类).

    依据标题关键词启发式: 真实 architecture 不给 chapter 打 role 标签, 用主题型 title
    建模, 结构章节标题就是 '封面'/'目录'/'致谢' 这类短词.
    """
    title = (chapter.get("title") or "").lower()
    return any(kw in title for kw in _STRUCTURAL_TITLE_KEYWORDS)


def _validate_safe_name(name: str, kind: str) -> None:
    """Reject ".." / absolute paths / quotes / 任何非简单标识符的名字 (防 path traversal)."""
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid {kind} name: {name!r}. Must match {_SAFE_NAME_RE.pattern}."
        )


def load_parsed_content(path: str) -> dict:
    """Load parsed-content.json."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_preset(name: str) -> dict:
    """Load preset YAML by name. name 限简单标识符防 path traversal."""
    _validate_safe_name(name, "preset")
    preset_path = PRESETS_DIR / f"{name}.yaml"
    if not preset_path.exists():
        print(f"ERROR: Preset not found: {preset_path}", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(preset_path.read_text(encoding="utf-8"))


def validate_architecture(arch: dict, preset: dict) -> list[str]:
    """Validate content-architecture against preset rules.

    Returns list of issue descriptions (empty = valid).
    """
    issues = []
    rules = preset.get("content_rules", {})
    chapters = arch.get("chapters", []) or []

    # Check title style — 仅校验内容章节, 结构章节 (封面/目录/致谢) 豁免.
    # 2026-06-15 校准 (issue-ppt-validate-architecture-overstrict): 章节标题是主题型短语,
    # 不是 slide 级行动标题; 原 >=10 字启发式误伤真实华为风格 (9 字主题词). 改为只拦退化标题.
    if rules.get("title_style") == "action_title":
        for ch in chapters:
            if _is_structural_chapter(ch):
                continue
            title = (ch.get("title") or "").strip()
            if len(title) < _MIN_CONTENT_CHAPTER_TITLE:
                issues.append(
                    f"Chapter '{title}' title 过短 (< {_MIN_CONTENT_CHAPTER_TITLE} 字), "
                    f"内容章节标题应为有意义的主题短语"
                )

    # Check total slides reasonable
    total = arch.get("total_slides", 0)
    if total < 3:
        issues.append(f"total_slides={total} too few for a meaningful presentation")
    if total > 40:
        issues.append(f"total_slides={total} exceeds recommended max (40)")

    # Check required sections covered.
    # 2026-06-15 校准 (issue-ppt-validate-architecture-overstrict): 真实 architecture 不给
    # chapter 打 role 标签, 用主题型 title + slide_briefs 建模. 原版要求 executive_summary/
    # content/recommendations 等 role 字面命中, 对真实满意产物全 false-positive. role 覆盖按
    # 三层放宽: (1) 显式 chapter.role 命中 (2) title 含 role 关键词 (3) 存在内容章节即视为
    # 内容型 role 已覆盖 (识别真实建模方式). 仅当 architecture 无任何内容章节时才报 unmet —
    # 既消除误报, 又保留对退化 architecture (无章节) 的拦截. title/closing 由 render always-create, skip.
    required_roles = [s.get("role", "") for s in preset.get("structure", {}).get("required_sections", [])]
    chapter_roles = {(ch.get("role") or "").lower() for ch in chapters}
    chapter_titles_lower = " ".join((ch.get("title") or "").lower() for ch in chapters)
    has_content_chapter = any(
        (not _is_structural_chapter(ch)) and (ch.get("slide_briefs"))
        for ch in chapters
    )
    for r in required_roles:
        r_lower = r.lower()
        if r_lower in ("title", "closing"):
            # title/closing slide always created by render 阶段, skip
            continue
        explicit = r_lower in chapter_roles or r_lower in chapter_titles_lower
        if not explicit and not has_content_chapter:
            issues.append(
                f"Required content section role={r!r} 未覆盖 (architecture 无内容章节)"
            )

    return issues


def main():
    parser = argparse.ArgumentParser(description="Architect stage utilities")
    sub = parser.add_subparsers(dest="command")

    load_cmd = sub.add_parser("load")
    load_cmd.add_argument("parsed_content", help="Path to parsed-content.json")
    load_cmd.add_argument("--preset", default="research-report")

    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("architecture", help="Path to content-architecture.yaml")
    validate_cmd.add_argument("--preset", default="research-report")

    args = parser.parse_args()

    if args.command == "load":
        content = load_parsed_content(args.parsed_content)
        preset = load_preset(args.preset)
        print(json.dumps({
            "assets": content.get("assets", {}),
            "source_count": len(content.get("sources", [])),
            "preset": preset.get("name", args.preset),
            "content_rules": preset.get("content_rules", {}),
        }, ensure_ascii=False, indent=2))

    elif args.command == "validate":
        arch = yaml.safe_load(Path(args.architecture).read_text(encoding="utf-8"))
        preset = load_preset(args.preset)
        issues = validate_architecture(arch, preset)
        if issues:
            print("Validation issues:", file=sys.stderr)
            for issue in issues:
                print(f"  - {issue}", file=sys.stderr)
            sys.exit(1)
        else:
            print("Architecture validation passed.")


if __name__ == "__main__":
    main()
