# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0", "Pillow>=10.0"]
# ///
"""parse.py: Stage 1 of ppt pipeline - multi-format content parsing.

Recursively scans input directory, parses supported file formats,
and produces parsed-content.json.

MVP supports: .md (markdown), .png/.jpg/.svg (image assets)
Phase 2 adds: .docx, .xlsx, .csv, .pdf

Usage:
    uv run --script engine/parse.py <input-path> --output parsed-content.json
"""

import argparse
import json
import re
import sys
from pathlib import Path


def parse_markdown(filepath: Path) -> dict:
    """Parse .md file into content blocks."""
    text = filepath.read_text(encoding="utf-8")
    blocks = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Heading
        heading_match = re.match(r'^(#{1,6})\s+(.*)', line)
        if heading_match:
            level = len(heading_match.group(1))
            blocks.append({"type": "heading", "level": level, "text": heading_match.group(2).strip()})
            i += 1
            continue

        # Code block
        if line.strip().startswith("```"):
            lang_match = re.match(r'^```(\w*)', line.strip())
            language = lang_match.group(1) if lang_match else ""
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append({"type": "code", "language": language, "text": "\n".join(code_lines)})
            i += 1  # skip closing ```
            continue

        # Table
        if "|" in line and i + 1 < len(lines) and re.match(r'^[\s|:-]+$', lines[i + 1]):
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # skip header and separator
            rows = []
            while i < len(lines) and "|" in lines[i]:
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(row)
                i += 1
            blocks.append({"type": "table", "headers": headers, "rows": rows})
            continue

        # Blockquote
        if line.strip().startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append({"type": "blockquote", "text": "\n".join(quote_lines)})
            continue

        # List (unordered or ordered)
        list_match = re.match(r'^(\s*)([-*]|\d+\.)\s+(.*)', line)
        if list_match:
            items = []
            while i < len(lines):
                lm = re.match(r'^(\s*)([-*]|\d+\.)\s+(.*)', lines[i])
                if not lm:
                    break
                items.append(lm.group(3).strip())
                i += 1
            blocks.append({"type": "list", "items": items})
            continue

        # Paragraph (non-empty lines)
        if line.strip():
            para_lines = []
            while i < len(lines) and lines[i].strip() and not re.match(r'^(#{1,6}\s|[-*]\s|\d+\.\s|>|```|\|)', lines[i]):
                para_lines.append(lines[i].strip())
                i += 1
            blocks.append({"type": "paragraph", "text": " ".join(para_lines)})
            continue

        # Empty line
        i += 1

    return {
        "file": str(filepath),
        "type": "markdown",
        "content_blocks": blocks,
    }


def _parse_svg_dimensions(filepath: Path) -> tuple[int | None, int | None]:
    """Try to extract width/height from SVG viewBox or width/height attributes."""
    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        # Try viewBox first: "minX minY width height"
        vb = root.get("viewBox")
        if vb:
            parts = vb.split()
            if len(parts) == 4:
                return int(float(parts[2])), int(float(parts[3]))
        # Try width/height attributes (strip units like "px")
        w_attr = root.get("width", "")
        h_attr = root.get("height", "")
        if w_attr and h_attr:
            w_val = re.sub(r'[^0-9.]', '', w_attr)
            h_val = re.sub(r'[^0-9.]', '', h_attr)
            if w_val and h_val:
                return int(float(w_val)), int(float(h_val))
    except Exception:
        pass
    return None, None


def parse_image(filepath: Path) -> dict:
    """Register image asset with dimensions."""
    ext = filepath.suffix.lower()
    if ext == ".svg":
        w, h = _parse_svg_dimensions(filepath)
        return {
            "file": str(filepath),
            "type": "image",
            "width": w,
            "height": h,
            "ai_description": "",
            "suggested_usage": suggest_image_usage(w, h) if w and h else "full-page-exhibit",
        }
    from PIL import Image
    img = Image.open(filepath)
    w, h = img.size
    return {
        "file": str(filepath),
        "type": "image",
        "width": w,
        "height": h,
        "ai_description": "",  # filled by SKILL.md (AI generates description)
        "suggested_usage": suggest_image_usage(w, h),
    }


def suggest_image_usage(w: int, h: int) -> str:
    """Suggest how an image should be used based on aspect ratio."""
    ratio = w / h if h > 0 else 1.0
    if ratio > 2.0:
        return "banner"
    elif ratio > 1.2:
        return "full-page-exhibit"
    elif ratio > 0.8:
        return "half-page"
    else:
        return "sidebar"


def estimate_volume(sources: list) -> str:
    """Estimate content volume from parsed sources."""
    total_chars = sum(
        sum(len(b.get("text", "")) for b in s.get("content_blocks", []))
        for s in sources if s.get("type") == "markdown"
    )
    if total_chars > 10000:
        return "large"
    elif total_chars > 3000:
        return "medium"
    return "small"


def main(input_path: str, output: str) -> None:
    """Main entry point: parse input path and write parsed-content.json."""
    path = Path(input_path)

    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.rglob("*"))
    else:
        print(f"ERROR: Path not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    sources = []
    for f in files:
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext == ".md":
            sources.append(parse_markdown(f))
        elif ext in (".png", ".jpg", ".jpeg", ".svg"):
            sources.append(parse_image(f))
        # Phase 2: elif ext == ".docx": ...

    assets = {
        "total_files": len([f for f in files if f.is_file()]),
        "text_sources": sum(1 for s in sources if s["type"] == "markdown"),
        "image_assets": sum(1 for s in sources if s["type"] == "image"),
        "estimated_content_volume": estimate_volume(sources),
    }

    result = {"sources": sources, "assets": assets}
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Parsed {len(sources)} sources -> {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 1: Multi-format content parsing")
    parser.add_argument("input_path", help="Input file or directory")
    parser.add_argument("--output", default="parsed-content.json", help="Output JSON path")
    args = parser.parse_args()
    main(args.input_path, args.output)
