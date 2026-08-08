# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pymupdf>=1.24",
# ]
# ///
"""从教材 PDF 按指定页范围截取为独立子 PDF + 逐页渲染为高 DPI PNG。

Usage:
    uv run --script extract_pages.py \\
        --pdf "D:/path/to/textbook.pdf" \\
        --start 49 --end 55 \\
        --output-dir "D:/path/to/extracted" \\
        --chapter-name "周长" \\
        --dpi 400
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF


def main() -> None:
    parser = argparse.ArgumentParser(
        description="截取 PDF 页范围并渲染为高 DPI PNG"
    )
    parser.add_argument("--pdf", required=True, help="PDF 绝对路径")
    parser.add_argument(
        "--start", type=int, required=True,
        help="起始页（PDF 物理页，从 1 开始，包含）"
    )
    parser.add_argument(
        "--end", type=int, required=True,
        help="结束页（PDF 物理页，包含）"
    )
    parser.add_argument(
        "--output-dir", required=True, help="输出目录"
    )
    parser.add_argument(
        "--chapter-name", default="chapter",
        help='章节名，用于子 PDF 文件名（默认 "chapter"）'
    )
    parser.add_argument(
        "--dpi", type=int, default=400,
        help="PNG 渲染 DPI（默认 400）"
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        sys.exit(f"PDF 文件不存在: {pdf_path}")

    out_dir = Path(args.output_dir)
    pages_dir = out_dir / "pages"
    assets_dir = out_dir / "assets"
    pages_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    chapter_pdf = out_dir / f"{args.chapter_name}_章节.pdf"

    doc = fitz.open(str(pdf_path))
    total = doc.page_count
    print(f"PDF 总页数: {total}")

    if args.start < 1:
        sys.exit(f"起始页必须 >= 1，当前为 {args.start}")
    if args.end < args.start:
        sys.exit(f"结束页 ({args.end}) 必须 >= 起始页 ({args.start})")
    if args.end > total:
        sys.exit(f"结束页超出范围: 目标 {args.end}，PDF 只有 {total} 页")

    zoom = args.dpi / 72
    mat = fitz.Matrix(zoom, zoom)

    sub_doc = fitz.open()

    for human_page in range(args.start, args.end + 1):
        idx = human_page - 1
        page = doc.load_page(idx)

        pix = page.get_pixmap(matrix=mat, alpha=False)
        png_path = pages_dir / f"page_{human_page:03d}.png"
        pix.save(str(png_path))
        print(f"渲染 p.{human_page} -> {png_path.name}  ({pix.width}x{pix.height})")

        sub_doc.insert_pdf(doc, from_page=idx, to_page=idx)

    sub_doc.save(str(chapter_pdf))
    sub_doc.close()
    doc.close()

    print("")
    print(f"子 PDF 保存至: {chapter_pdf}")
    print(f"PNG 目录:     {pages_dir}")
    print(f"资源目录:     {assets_dir}")
    print(f"共渲染 {args.end - args.start + 1} 页")


if __name__ == "__main__":
    main()
