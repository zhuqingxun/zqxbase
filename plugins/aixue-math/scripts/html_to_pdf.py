# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.40"]
# ///
"""html_to_pdf.py — 用 Playwright Chromium 把 HTML 打印为 PDF

产出 PDF 保留 HTML 的 CSS 样式（包括 @media print 规则）、KaTeX/Mermaid 渲染结果。
相比 pandoc + LaTeX 方案，更适合含 Mermaid 图、Web 字体、复杂 CSS 的现代网页。

用法：
    uv run --script html_to_pdf.py <input.html> <output.pdf>
           [--margin 20mm] [--format A4] [--wait-ms 3000]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def html_to_pdf(
    input_html: Path,
    output_pdf: Path,
    margin: str = "20mm",
    page_format: str = "A4",
    wait_ms: int = 3000,
) -> None:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    # 统一 margin 四边
    margins = {"top": margin, "right": margin, "bottom": margin, "left": margin}

    uri = input_html.resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        # 用 load 而非 networkidle——KaTeX/Mermaid CDN 异步轮询会让 networkidle 超时
        page.goto(uri, wait_until="load", timeout=60000)
        # 等 Mermaid 渲染完成。两道门必须同时成立才算完成：
        #   ① 初始化脚本已把 <pre class="mermaid"> 替换为 <div class="mermaid">
        #      （否则下面查 div.mermaid 数量为 0 就会立刻 return true，假阴性）
        #   ② 所有 div.mermaid 都已渲染出 svg（或带 data-processed=true 标记）
        # 复杂 flowchart（多节点/中文 label/dotted edge）渲染可能需要几秒，超时给 60s。
        page.wait_for_function(
            """() => {
                // 门 ①: 初始化脚本必须跑完（无 pre.mermaid 残留）
                const remaining = document.querySelectorAll(
                    'pre.mermaid, pre > code.mermaid, pre > code.language-mermaid'
                );
                if (remaining.length > 0) return false;
                // 门 ②: 所有 div.mermaid 都已渲染
                const divs = document.querySelectorAll('div.mermaid');
                if (divs.length === 0) return true;
                return Array.from(divs).every(n =>
                    n.querySelector('svg') || n.getAttribute('data-processed') === 'true'
                );
            }""",
            timeout=60000,
        )
        # 再给 KaTeX/字体等余量
        page.wait_for_timeout(wait_ms)
        page.pdf(
            path=str(output_pdf),
            format=page_format,
            margin=margins,
            print_background=True,
            prefer_css_page_size=False,
        )
        browser.close()

    size = output_pdf.stat().st_size
    print(f"wrote {output_pdf} ({size:,} bytes)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_html")
    ap.add_argument("output_pdf")
    ap.add_argument("--margin", default="20mm", help="页边距（默认 20mm）")
    ap.add_argument("--format", default="A4", dest="page_format", help="页面规格（A4/Letter）")
    ap.add_argument("--wait-ms", type=int, default=3000, help="等 JS 渲染完成毫秒数")
    args = ap.parse_args()

    inp = Path(args.input_html).resolve()
    if not inp.is_file():
        print(f"ERROR: 输入不存在: {inp}", file=sys.stderr)
        sys.exit(1)

    out = Path(args.output_pdf).resolve()
    html_to_pdf(inp, out, margin=args.margin, page_format=args.page_format, wait_ms=args.wait_ms)


if __name__ == "__main__":
    main()
