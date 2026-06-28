# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pypdfium2>=4.30",
# ]
# ///
"""pdf_extract.py — PDF 文本提取 wrapper

基于 pypdfium2（实测为 mint workspace 访谈提纲 PDF 唯一无乱码方案）。
提供函数导入 + CLI 双接口。

CLI:
    uv run --script pdf_extract.py <pdf_path>
    stdout: 纯文本；exit 0 = 成功；exit 2 = 失败（不存在 / 提取空 / 异常）

作为 import 时使用 extract_pdf_text(path) 函数。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pypdfium2 as pdfium


def extract_pdf_text(path: Path) -> str:
    """提取 PDF 所有页面的文本，以换行拼接

    失败抛异常，交由调用方处理。空文档返回空字符串（不抛）。
    """
    pdf = pdfium.PdfDocument(str(path))
    try:
        parts: list[str] = []
        for page in pdf:
            textpage = page.get_textpage()
            try:
                parts.append(textpage.get_text_range())
            finally:
                textpage.close()
            page.close()
        return "\n".join(parts)
    finally:
        pdf.close()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("ERROR: 用法: pdf_extract.py <pdf_path>", file=sys.stderr)
        return 2
    p = Path(argv[0])
    if not p.exists() or not p.is_file():
        print(f"ERROR: 文件不存在: {p}", file=sys.stderr)
        return 2
    try:
        text = extract_pdf_text(p)
    except Exception as e:
        print(f"ERROR: PDF 解析失败: {e}", file=sys.stderr)
        return 2
    if len(text.strip()) < 100:
        print(
            "ERROR: PDF 文本提取结果过短（疑似加密 / 扫描件无文本层）",
            file=sys.stderr,
        )
        return 2
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
