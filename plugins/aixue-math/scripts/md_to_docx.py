# /// script
# requires-python = ">=3.10"
# dependencies = ["python-docx>=1.1"]
# ///
"""md_to_docx.py — aixue-math 教案 Markdown → Word docx 的完整流水线

流水线（方案 2 / 目标架构）：
    md  →  pandoc (--filter mermaid-filter + --reference-doc)  →  docx (初稿)
        →  postprocess_docx.py (表格边框 + 东亚字体提示 + 粗体字体强化)
        →  docx (最终)

默认行为：
    - 自动查找 reference.docx（plugin references/lesson-plan-reference.docx）
    - 自动启用 mermaid-filter（把 mermaid 代码块编译为 PNG 内嵌）
    - 自动执行 postprocess_docx.py 后处理

用法：
    uv run --script md_to_docx.py <input.md> <output.docx>
           [--reference-doc <ref.docx>] [--no-reference]
           [--no-mermaid] [--no-postprocess]
           [--lang zh-CN]
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def find_pandoc() -> str:
    p = shutil.which("pandoc")
    if not p:
        print(
            "ERROR: pandoc 未安装。Windows: winget install JohnMacFarlane.Pandoc",
            file=sys.stderr,
        )
        sys.exit(1)
    return p


def find_mermaid_filter() -> str | None:
    """mermaid-filter 的路径。Windows 下 pandoc 需要 .cmd 版本。"""
    if platform.system() == "Windows":
        for candidate in [
            shutil.which("mermaid-filter.cmd"),
            Path(os.path.expanduser("~/AppData/Roaming/npm/mermaid-filter.cmd")),
        ]:
            if candidate and Path(candidate).is_file():
                return str(candidate)
    else:
        p = shutil.which("mermaid-filter")
        if p:
            return p
    return None


DEFAULT_REFERENCE_FILENAME = "lesson-plan-reference.docx"


def auto_find_reference_doc(script_path: Path) -> Path | None:
    """从脚本位置推导默认 reference.docx。"""
    for c in [
        script_path.parent.parent / "references" / DEFAULT_REFERENCE_FILENAME,
        script_path.parent / DEFAULT_REFERENCE_FILENAME,
    ]:
        if c.is_file():
            return c
    return None


def auto_find_postprocess_script(script_path: Path) -> Path | None:
    p = script_path.parent / "postprocess_docx.py"
    return p if p.is_file() else None


def run_pandoc(
    pandoc: str,
    input_md: Path,
    output_docx: Path,
    reference_doc: Path | None,
    mermaid_filter: str | None,
    lang: str,
) -> None:
    cmd = [
        pandoc,
        str(input_md),
        "-o",
        str(output_docx),
        "--from",
        "gfm+yaml_metadata_block",
        "-V",
        f"lang={lang}",
    ]
    if reference_doc:
        cmd.extend(["--reference-doc", str(reference_doc)])
    if mermaid_filter:
        cmd.extend(["--filter", mermaid_filter])

    # mermaid-filter 需在 md 所在目录运行（它会把中间图片和日志写到那里）
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=input_md.parent)
    if result.returncode != 0:
        print(f"ERROR: pandoc failed ({result.returncode})\n{result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)

    # 清理 mermaid-filter 留下的 .err 日志（成功运行时无内容）
    err_log = input_md.parent / "mermaid-filter.err"
    if err_log.is_file() and err_log.stat().st_size == 0:
        err_log.unlink()


def run_postprocess(script_path: Path, docx_path: Path) -> None:
    result = subprocess.run(
        ["uv", "run", "--script", str(script_path), str(docx_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"WARNING: postprocess failed ({result.returncode})\n{result.stderr}", file=sys.stderr)
        return
    if result.stdout.strip():
        print(result.stdout.strip())


def convert(
    input_md: Path,
    output_docx: Path,
    reference_doc: Path | None = None,
    use_mermaid: bool = True,
    use_postprocess: bool = True,
    lang: str = "zh-CN",
) -> None:
    pandoc = find_pandoc()
    output_docx.parent.mkdir(parents=True, exist_ok=True)

    mermaid_filter = find_mermaid_filter() if use_mermaid else None
    if use_mermaid and not mermaid_filter:
        print("WARNING: mermaid-filter 未安装，mermaid 代码块将保留为代码文本", file=sys.stderr)

    run_pandoc(pandoc, input_md, output_docx, reference_doc, mermaid_filter, lang)

    tags = []
    if reference_doc:
        tags.append(f"ref={reference_doc.name}")
    if mermaid_filter:
        tags.append("mermaid")

    if use_postprocess:
        script = auto_find_postprocess_script(Path(__file__).resolve())
        if script:
            run_postprocess(script, output_docx)
            tags.append("postprocessed")
        else:
            print("WARNING: postprocess_docx.py 未找到，跳过后处理", file=sys.stderr)

    size = output_docx.stat().st_size
    tag_str = f" [{', '.join(tags)}]" if tags else ""
    print(f"wrote {output_docx} ({size:,} bytes){tag_str}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="将 Markdown 教案转为 Word docx（基于 pandoc）"
    )
    ap.add_argument("input_md", help="输入 Markdown 文件路径")
    ap.add_argument("output_docx", help="输出 docx 文件路径")
    ap.add_argument("--reference-doc", default=None, help="自定义样式模板 docx")
    ap.add_argument("--no-reference", action="store_true", help="禁用默认模板")
    ap.add_argument("--no-mermaid", action="store_true", help="禁用 mermaid-filter")
    ap.add_argument("--no-postprocess", action="store_true", help="禁用 python-docx 后处理")
    ap.add_argument("--lang", default="zh-CN", help="语言标签（默认 zh-CN）")
    args = ap.parse_args()

    inp = Path(args.input_md).resolve()
    if not inp.is_file():
        print(f"ERROR: 输入文件不存在: {inp}", file=sys.stderr)
        sys.exit(1)

    out = Path(args.output_docx).resolve()

    if args.no_reference:
        ref = None
    elif args.reference_doc:
        ref = Path(args.reference_doc).resolve()
        if not ref.is_file():
            print(f"WARNING: reference-doc 不存在: {ref}", file=sys.stderr)
            ref = None
    else:
        ref = auto_find_reference_doc(Path(__file__).resolve())
        if ref is None:
            print("WARNING: 未找到默认模板 lesson-plan-reference.docx", file=sys.stderr)

    convert(
        inp,
        out,
        reference_doc=ref,
        use_mermaid=not args.no_mermaid,
        use_postprocess=not args.no_postprocess,
        lang=args.lang,
    )


if __name__ == "__main__":
    main()
