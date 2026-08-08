# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""generate_all_formats.py — aixue-math 教案 md → docx + html + pdf 三通道一次产出

流水线：
    input.md  ─┬──► md_to_docx.py    ──►  docx/*.docx
               ├──► md_to_html.py    ──►  html/*.html
               │                          (html 是 pdf 的输入)
               └──► html_to_pdf.py   ──►  pdf/*.pdf

用法：
    uv run --script generate_all_formats.py <input.md> [--output-base <dir>]
           [--skip-docx] [--skip-html] [--skip-pdf]

目录约定（按格式分子目录，最新版在 05_教案 根，历史进 OLD/）：
    workspace_root/05_教案/md/v<V>-课时<K>-<title>.md
        →  workspace_root/05_教案/docx/v<V>-课时<K>-<title>.docx
        →  workspace_root/05_教案/html/v<V>-课时<K>-<title>.html
        →  workspace_root/05_教案/pdf/v<V>-课时<K>-<title>.pdf

自动从 input.md（在 05_教案/md/）推导同级的 docx/html/pdf 目录。
导出后由 `workspace_io.py rotate-versions` 把旧版本降级到 05_教案/OLD/。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent


def run_step(label: str, cmd: list[str]) -> bool:
    print(f"--- [{label}] ---")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        print(f"FAILED [{label}] exit={result.returncode}", file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_md")
    ap.add_argument("--output-base", default=None, help="05_教案/ 目录；省略则取 input.md 的祖父目录（05_教案/md/x.md → 05_教案/）")
    ap.add_argument("--skip-docx", action="store_true")
    ap.add_argument("--skip-html", action="store_true")
    ap.add_argument("--skip-pdf", action="store_true")
    args = ap.parse_args()

    inp = Path(args.input_md).resolve()
    if not inp.is_file():
        print(f"ERROR: 输入不存在: {inp}", file=sys.stderr)
        sys.exit(1)

    # 推导输出路径
    # 标准约定：inp 在 .../05_教案/md/xxx.md
    # 同级格式目录：.../05_教案/{docx,html,pdf}
    if args.output_base:
        base = Path(args.output_base).resolve()  # 期望指向 05_教案/ 目录
    else:
        base = inp.parent.parent  # 05_教案/md/x.md → 05_教案/
    docx_dir = base / "docx"
    html_dir = base / "html"
    pdf_dir = base / "pdf"

    stem = inp.stem  # 如 v1-课时1-什么是周长-认识与测量
    docx_path = docx_dir / f"{stem}.docx"
    html_path = html_dir / f"{stem}.html"
    pdf_path = pdf_dir / f"{stem}.pdf"

    print(f"input : {inp}")
    print(f"docx  : {docx_path}")
    print(f"html  : {html_path}")
    print(f"pdf   : {pdf_path}")
    print()

    summary = {}

    # docx
    if not args.skip_docx:
        ok = run_step(
            "docx",
            ["uv", "run", "--script", str(SCRIPTS_DIR / "md_to_docx.py"),
             str(inp), str(docx_path)],
        )
        summary["docx"] = "✅" if ok and docx_path.is_file() else "❌"

    # html
    if not args.skip_html:
        ok = run_step(
            "html",
            ["uv", "run", "--script", str(SCRIPTS_DIR / "md_to_html.py"),
             str(inp), str(html_path)],
        )
        summary["html"] = "✅" if ok and html_path.is_file() else "❌"

    # pdf（依赖 html）
    if not args.skip_pdf:
        if html_path.is_file():
            ok = run_step(
                "pdf",
                ["uv", "run", "--script", str(SCRIPTS_DIR / "html_to_pdf.py"),
                 str(html_path), str(pdf_path), "--wait-ms", "5000"],
            )
            summary["pdf"] = "✅" if ok and pdf_path.is_file() else "❌"
        else:
            summary["pdf"] = "⚠ skipped (no html)"

    # 汇总
    print()
    print("=" * 50)
    for fmt, status in summary.items():
        path = {"docx": docx_path, "html": html_path, "pdf": pdf_path}[fmt]
        size = f"{path.stat().st_size:,}" if path.is_file() else "-"
        print(f"  {status}  {fmt:4s}  {size:>12s} bytes  {path.name}")
    print("=" * 50)


if __name__ == "__main__":
    main()
