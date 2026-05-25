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

    # Check title style
    if rules.get("title_style") == "action_title":
        for ch in arch.get("chapters", []):
            title = ch.get("title", "")
            # Action title should be a complete sentence (heuristic: >10 chars)
            if len(title) < 10:
                issues.append(f"Chapter '{title}' title too short for action_title style")

    # Check total slides reasonable
    total = arch.get("total_slides", 0)
    if total < 3:
        issues.append(f"total_slides={total} too few for a meaningful presentation")
    if total > 40:
        issues.append(f"total_slides={total} exceeds recommended max (40)")

    # Check required sections covered
    # 2026-05-19 audit fix: 原版两个分支都是 `pass` no-op, chapters 变量算了不用 — 完全失效校验.
    # 现在真正检查 chapter.role (或 fallback 到 title 启发式) 是否覆盖 preset 声明的 required_sections.
    # title / closing 由 render 阶段 always create, 此处仅校验内容章节的 required_sections.
    required_roles = [s.get("role", "") for s in preset.get("structure", {}).get("required_sections", [])]
    chapter_roles = {(ch.get("role") or "").lower() for ch in arch.get("chapters", [])}
    chapter_titles_lower = " ".join(ch.get("title", "").lower() for ch in arch.get("chapters", []))
    for r in required_roles:
        r_lower = r.lower()
        if r_lower in ("title", "closing"):
            # title/closing slide always created by render 阶段, skip
            continue
        # 章节 role 字段命中 OR 标题文本包含 role 关键词 (启发式)
        if r_lower not in chapter_roles and r_lower not in chapter_titles_lower:
            issues.append(f"Required section role={r!r} not found in architecture chapters")

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
