# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""md_to_html.py — Markdown 教案 → 自包含 HTML（图文并茂）

特性：
  - pandoc 生成 HTML5，--embed-resources 把图片 base64 化（单文件分发）
  - 自定义 CSS（教学设计风：彩色标题、表格边框、代码卡片、图片边框阴影）
  - Mermaid 客户端渲染（CDN jsdelivr，支持代码块 ```mermaid）
  - KaTeX 客户端渲染数学公式（$...$ 和 $$...$$）
  - 侧栏 TOC 目录（toc-depth=3）
  - 打印友好 CSS（@media print）

用法：
    uv run --script md_to_html.py <input.md> <output.html> [--no-embed]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


CSS_CONTENT = r"""
html { scroll-behavior: smooth; }
body {
    font-family: "Microsoft YaHei", "Segoe UI", "SimSun", sans-serif;
    max-width: 920px;
    margin: 2em auto;
    padding: 0 1.5em;
    line-height: 1.7;
    color: #222;
    font-size: 15.5px;
    background: #fafbfc;
}
h1, h2, h3, h4 { font-family: "Microsoft YaHei", sans-serif; }
h1 {
    font-size: 2em;
    text-align: center;
    color: #2c3e50;
    border-bottom: 3px solid #c0392b;
    padding-bottom: 0.4em;
    margin-top: 0;
}
h2 {
    font-size: 1.55em;
    color: #2c3e50;
    border-left: 6px solid #3498db;
    padding: 0.1em 0.6em;
    margin-top: 2.2em;
    background: linear-gradient(to right, #eaf4fb, transparent);
}
h3 {
    font-size: 1.22em;
    color: #34495e;
    border-bottom: 1px dashed #bdc3c7;
    padding-bottom: 0.3em;
    margin-top: 1.8em;
}
h4 {
    font-size: 1.08em;
    color: #555;
    margin-top: 1.4em;
}
p, li { margin: 0.5em 0; }
strong { color: #c0392b; }
em { color: #2980b9; }
hr { border: 0; border-top: 1px dashed #bbb; margin: 2em 0; }

/* 表格 */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: 0.92em;
    background: #fff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
thead { background: #2c3e50; color: #fff; }
th, td {
    border: 1px solid #cbd5e0;
    padding: 0.55em 0.8em;
    text-align: left;
    vertical-align: top;
}
tbody tr:nth-child(even) td { background: #f7fafc; }

/* 代码 */
code {
    background: #eef2f5;
    padding: 0.1em 0.35em;
    border-radius: 3px;
    font-family: Consolas, "Courier New", monospace;
    font-size: 0.92em;
    color: #c7254e;
}
pre {
    background: #282c34;
    color: #abb2bf;
    padding: 1em 1.2em;
    border-radius: 6px;
    overflow-x: auto;
    box-shadow: 0 2px 8px rgba(0,0,0,0.12);
}
pre code { background: none; color: inherit; padding: 0; font-size: 0.9em; }

/* 引用 */
blockquote {
    border-left: 5px solid #e67e22;
    padding: 0.7em 1.2em;
    color: #555;
    background: #fef9e7;
    margin: 1em 0;
    border-radius: 0 4px 4px 0;
}
blockquote p:first-child { margin-top: 0; }
blockquote p:last-child { margin-bottom: 0; }

/* 图片 */
img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1.2em auto;
    border: 1px solid #ddd;
    border-radius: 6px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.08);
}

/* Mermaid */
.mermaid {
    text-align: center;
    margin: 1.5em auto;
    padding: 1em;
    background: #fff;
    border: 1px solid #e5e9ef;
    border-radius: 6px;
}

/* 目录 */
#TOC {
    background: #fff;
    border: 1px solid #e5e9ef;
    border-radius: 6px;
    padding: 1em 1.3em;
    margin: 1.5em 0 2em;
}
#TOC > ul { padding-left: 1em; }
#TOC::before {
    content: "📋 目录";
    display: block;
    font-weight: bold;
    color: #2c3e50;
    margin-bottom: 0.6em;
    font-size: 1.08em;
}
#TOC a { color: #2980b9; text-decoration: none; }
#TOC a:hover { text-decoration: underline; }

/* KaTeX inline adjust */
.katex { font-size: 1.05em; }

/* 打印友好 */
@media print {
    body { max-width: 100%; margin: 0; padding: 0 1cm; background: #fff; font-size: 11pt; }
    h2 { page-break-after: avoid; }
    table, img, .mermaid { page-break-inside: avoid; }
    pre { page-break-inside: avoid; }
    blockquote { page-break-inside: avoid; }
    #TOC { page-break-after: always; }
}
"""


HEADER_HTML = """
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body, { delimiters: [
            {left: '$$', right: '$$', display: true},
            {left: '$', right: '$', display: false},
            {left: '\\\\(', right: '\\\\)', display: false},
            {left: '\\\\[', right: '\\\\]', display: true}
        ]});"></script>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({ startOnLoad: false, theme: 'default', fontFamily: '"Microsoft YaHei", sans-serif' });
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('pre > code.mermaid, pre > code.language-mermaid, pre.mermaid').forEach(el => {
      const div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = el.textContent;
      const target = el.tagName === 'PRE' ? el : el.parentElement;
      target.replaceWith(div);
    });
    mermaid.run();
  });
</script>
"""


def find_pandoc() -> str:
    p = shutil.which("pandoc")
    if not p:
        print("ERROR: pandoc 未安装", file=sys.stderr)
        sys.exit(1)
    return p


def convert(input_md: Path, output_html: Path, embed: bool = True) -> None:
    pandoc = find_pandoc()
    output_html.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        css_file = td_path / "style.css"
        css_file.write_text(CSS_CONTENT, encoding="utf-8")
        header_file = td_path / "header.html"
        header_file.write_text(HEADER_HTML, encoding="utf-8")

        cmd = [
            pandoc,
            str(input_md),
            "-o",
            str(output_html),
            "--from", "gfm+yaml_metadata_block",
            "-t", "html5",
            "--standalone",
            "--toc",
            "--toc-depth=3",
            "-c", str(css_file),
            "-H", str(header_file),
            "--metadata", "lang=zh-CN",
        ]
        if embed:
            cmd.append("--embed-resources")

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=input_md.parent)
        if result.returncode != 0:
            print(f"ERROR: pandoc failed ({result.returncode})\n{result.stderr}", file=sys.stderr)
            sys.exit(result.returncode)

    size = output_html.stat().st_size
    mode = "self-contained" if embed else "linked"
    print(f"wrote {output_html} ({size:,} bytes) [{mode}]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_md")
    ap.add_argument("output_html")
    ap.add_argument("--no-embed", action="store_true", help="不内嵌资源（图片用相对路径链接）")
    args = ap.parse_args()

    inp = Path(args.input_md).resolve()
    if not inp.is_file():
        print(f"ERROR: 输入不存在: {inp}", file=sys.stderr)
        sys.exit(1)

    out = Path(args.output_html).resolve()
    convert(inp, out, embed=not args.no_embed)


if __name__ == "__main__":
    main()
