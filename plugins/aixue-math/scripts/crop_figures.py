# /// script
# requires-python = ">=3.10"
# dependencies = ["Pillow>=10", "pyyaml>=6"]
# ///
"""crop_figures.py — 按 YAML 配置从教材页面 PNG 中裁出单图

用法：
    uv run --script crop_figures.py <config.yaml> [--pages-dir DIR] [--output-dir DIR]

配置格式：
    pages_dir: 相对/绝对路径到 pages/*.png
    output_dir: 输出目录
    figures:
      - id: fig_p36_1
        page: page_036.png
        bbox_pct: [13, 20, 72, 33]    # [x1, y1, x2, y2] 百分比
        caption: 活动一：描边（树叶+教材封面）
      - id: fig_p36_2
        page: page_036.png
        bbox_pct: [13, 35, 90, 57]
        caption: 活动二：认一认，说一说
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from PIL import Image


def crop_one(page_path: Path, bbox_pct: list[int], out_path: Path) -> tuple[int, int]:
    im = Image.open(page_path)
    w, h = im.size
    x1 = int(w * bbox_pct[0] / 100)
    y1 = int(h * bbox_pct[1] / 100)
    x2 = int(w * bbox_pct[2] / 100)
    y2 = int(h * bbox_pct[3] / 100)
    cropped = im.crop((x1, y1, x2, y2))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out_path, optimize=True)
    return cropped.size


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--pages-dir", default=None)
    ap.add_argument("--output-dir", default=None)
    args = ap.parse_args()

    cfg_path = Path(args.config).resolve()
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    pages_dir = Path(args.pages_dir or cfg.get("pages_dir", "."))
    if not pages_dir.is_absolute():
        pages_dir = cfg_path.parent / pages_dir
    output_dir = Path(args.output_dir or cfg.get("output_dir", "./figures"))
    if not output_dir.is_absolute():
        output_dir = cfg_path.parent / output_dir

    print(f"pages from: {pages_dir}")
    print(f"output to:  {output_dir}")

    manifest = []
    for fig in cfg.get("figures", []):
        fig_id = fig["id"]
        page = fig["page"]
        bbox = fig["bbox_pct"]
        caption = fig.get("caption", "")
        page_path = pages_dir / page
        if not page_path.is_file():
            print(f"  SKIP {fig_id}: 页面不存在 {page_path}", file=sys.stderr)
            continue
        out_path = output_dir / f"{fig_id}.png"
        size = crop_one(page_path, bbox, out_path)
        print(f"  {fig_id}.png  {size[0]}x{size[1]}  « {page} bbox_pct={bbox}  — {caption}")
        manifest.append({"id": fig_id, "file": f"{fig_id}.png", "page": page, "caption": caption})

    manifest_path = output_dir / "figures.yaml"
    manifest_path.write_text(
        yaml.safe_dump({"figures": manifest}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"wrote manifest: {manifest_path}")


if __name__ == "__main__":
    main()
