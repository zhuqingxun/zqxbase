# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.0", "pyyaml>=6.0"]
# ///
"""plan.py: Stage 3 utilities - visual planning helpers.

Provides:
- Load theme YAML
- Load content-architecture.yaml
- Validate slide-plan.yaml against schema
- Visual type suggestion based on content analysis

The actual visual planning is done by AI (Claude) in the SKILL.md prompt.
This script provides helper functions for data I/O and validation.

Usage:
    # Load theme and architecture
    uv run --script engine/plan.py load <content-architecture.yaml> --theme <theme-name> --preset <preset-name>

    # Validate slide plan
    uv run --script engine/plan.py validate <slide-plan.yaml>
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parent.parent
THEMES_DIR = SKILLS_DIR / "themes"
PRESETS_DIR = SKILLS_DIR / "presets"

# PEP 723 standalone script: add parent dir so `from schemas.slide_plan` resolves
# when executed via `uv run --script`. Not needed if imported as a library module.
sys.path.insert(0, str(SKILLS_DIR))
from schemas.slide_plan import SlidePlan


def load_theme(name: str) -> dict:
    """Load theme YAML by name."""
    theme_path = THEMES_DIR / f"{name}.yaml"
    if not theme_path.exists():
        print(f"ERROR: Theme not found: {theme_path}", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(theme_path.read_text(encoding="utf-8"))


def load_architecture(path: str) -> dict:
    """Load content-architecture.yaml."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def validate_slide_plan(path: str) -> tuple[bool, str]:
    """Validate slide-plan.yaml against Pydantic schema.

    Returns (valid, message).
    """
    try:
        plan = SlidePlan.from_yaml(path)
        return True, f"Valid. {len(plan.slides)} slides, theme={plan.meta.theme}"
    except Exception as e:
        return False, str(e)


def suggest_visual_type(content_desc: str, preset_prefs: dict) -> str:
    """Suggest visual type based on content description keywords.

    Heuristic fallback - AI makes the actual decision.
    """
    desc = content_desc.lower()
    suggestions = {
        "process": "process-3-phase",
        "step": "process-3-phase",
        "compare": "comparison-2",
        "versus": "comparison-2",
        "metric": "data-contrast",
        "percent": "data-contrast",
        "quote": "quote-hero",
        "table": "table",
        "timeline": "timeline-horizontal",
    }
    for keyword, vtype in suggestions.items():
        if keyword in desc:
            return vtype
    return "bullets"


def main():
    parser = argparse.ArgumentParser(description="Plan stage utilities")
    sub = parser.add_subparsers(dest="command")

    load_cmd = sub.add_parser("load")
    load_cmd.add_argument("architecture", help="Path to content-architecture.yaml")
    load_cmd.add_argument("--theme", default="clean-light")
    load_cmd.add_argument("--preset", default="research-report")

    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("slide_plan", help="Path to slide-plan.yaml")

    args = parser.parse_args()

    if args.command == "load":
        arch = load_architecture(args.architecture)
        theme = load_theme(args.theme)
        preset_path = PRESETS_DIR / f"{args.preset}.yaml"
        preset = yaml.safe_load(preset_path.read_text(encoding="utf-8")) if preset_path.exists() else {}
        print(json.dumps({
            "thesis": arch.get("thesis", ""),
            "chapters": len(arch.get("chapters", [])),
            "total_slides": arch.get("total_slides", 0),
            "theme": theme.get("name", args.theme),
            "theme_colors": theme.get("colors", {}),
            "theme_typography": theme.get("typography", {}),
            "visual_type_preferences": preset.get("visual_type_preferences", {}),
        }, ensure_ascii=False, indent=2))

    elif args.command == "validate":
        valid, msg = validate_slide_plan(args.slide_plan)
        print(msg)
        if not valid:
            sys.exit(1)


if __name__ == "__main__":
    main()
