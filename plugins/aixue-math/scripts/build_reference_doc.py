# /// script
# requires-python = ">=3.10"
# dependencies = ["python-docx>=1.1"]
# ///
"""build_reference_doc.py — 定制 pandoc reference.docx 的中文教案样式

流程：
  1. 从 pandoc 导出默认 reference.docx（或以已有模板为基础）
  2. 本脚本修改标题/正文/代码/表格字体为中文友好样式
  3. 输出为最终 lesson-plan-reference.docx 供 md_to_docx.py 使用

默认风格（教学设计方案风格）：
  - Normal 正文：宋体 10.5pt 行距 1.5
  - Title  封面标题：黑体 18pt 黑色 居中
  - Heading 1：黑体 16pt 黑色（去掉 pandoc 默认蓝色）
  - Heading 2：黑体 14pt 黑色
  - Heading 3：黑体 12pt 黑色
  - Heading 4：宋体加粗 11pt 黑色
  - Verbatim / Source Code：Consolas 9.5pt（ASCII 艺术字保持等宽）
  - 表格：宋体 10pt 边框

用法：
    uv run --script build_reference_doc.py <input_ref.docx> <output_ref.docx>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor


CHINESE_SERIF = "Microsoft YaHei"   # 正文：微软雅黑（Win 自带，粗体清晰）
CHINESE_SANS = "Microsoft YaHei"    # 标题：同微软雅黑（靠 bold + 大字号区分）
MONO_FONT = "Consolas"              # 等宽：Consolas（代码块）


def set_run_fonts(rpr, ascii_font: str, east_asia_font: str) -> None:
    """在 <w:rPr> 下确保 <w:rFonts w:ascii=... w:hAnsi=... w:eastAsia=...> 就绪。"""
    rFonts = rpr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rpr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), ascii_font)
    rFonts.set(qn("w:hAnsi"), ascii_font)
    rFonts.set(qn("w:cs"), ascii_font)
    rFonts.set(qn("w:eastAsia"), east_asia_font)


def get_or_create_rpr(style_element):
    rPr = style_element.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        style_element.insert(0, rPr)
    return rPr


def set_color(rpr, hex_rgb: str) -> None:
    color = rpr.find(qn("w:color"))
    if color is None:
        color = OxmlElement("w:color")
        rpr.append(color)
    color.set(qn("w:val"), hex_rgb)


def set_size(rpr, half_pts: int) -> None:
    """w:sz 的单位是半磅。例如 16pt → 32。"""
    sz = rpr.find(qn("w:sz"))
    if sz is None:
        sz = OxmlElement("w:sz")
        rpr.append(sz)
    sz.set(qn("w:val"), str(half_pts))
    szCs = rpr.find(qn("w:szCs"))
    if szCs is None:
        szCs = OxmlElement("w:szCs")
        rpr.append(szCs)
    szCs.set(qn("w:val"), str(half_pts))


def set_bold(rpr, bold: bool = True) -> None:
    b = rpr.find(qn("w:b"))
    if bold:
        if b is None:
            b = OxmlElement("w:b")
            rpr.append(b)
        b.set(qn("w:val"), "1")
    else:
        if b is not None:
            rpr.remove(b)


def set_italic(rpr, italic: bool = False) -> None:
    i = rpr.find(qn("w:i"))
    if italic:
        if i is None:
            i = OxmlElement("w:i")
            rpr.append(i)
    else:
        if i is not None:
            rpr.remove(i)


def style_heading(
    style,
    pt_size: float,
    bold: bool = True,
    color_hex: str = "000000",
    sans: bool = True,
):
    rpr = get_or_create_rpr(style.element)
    set_run_fonts(
        rpr,
        ascii_font=CHINESE_SANS if sans else CHINESE_SERIF,
        east_asia_font=CHINESE_SANS if sans else CHINESE_SERIF,
    )
    set_size(rpr, int(pt_size * 2))
    set_bold(rpr, bold)
    set_italic(rpr, False)
    set_color(rpr, color_hex)


def style_normal(style, pt_size: float = 10.5, color_hex: str = "000000"):
    rpr = get_or_create_rpr(style.element)
    set_run_fonts(rpr, ascii_font=CHINESE_SERIF, east_asia_font=CHINESE_SERIF)
    set_size(rpr, int(pt_size * 2))
    set_bold(rpr, False)
    set_italic(rpr, False)
    set_color(rpr, color_hex)


def style_mono(style, pt_size: float = 9.5):
    rpr = get_or_create_rpr(style.element)
    set_run_fonts(rpr, ascii_font=MONO_FONT, east_asia_font=MONO_FONT)
    set_size(rpr, int(pt_size * 2))
    set_color(rpr, "000000")


def set_paragraph_spacing(style, space_before_pt: int, space_after_pt: int, line_rule: str = "auto", line_val: int = 360):
    pPr = style.element.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        style.element.insert(0, pPr)
    spacing = pPr.find(qn("w:spacing"))
    if spacing is None:
        spacing = OxmlElement("w:spacing")
        pPr.append(spacing)
    spacing.set(qn("w:before"), str(space_before_pt * 20))
    spacing.set(qn("w:after"), str(space_after_pt * 20))
    spacing.set(qn("w:line"), str(line_val))
    spacing.set(qn("w:lineRule"), line_rule)


def set_justification(style, val: str = "both") -> None:
    pPr = style.element.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        style.element.insert(0, pPr)
    jc = pPr.find(qn("w:jc"))
    if jc is None:
        jc = OxmlElement("w:jc")
        pPr.append(jc)
    jc.set(qn("w:val"), val)


def set_table_borders(style) -> None:
    """给 Table 样式加全边框。"""
    tblPr = style.element.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        style.element.append(tblPr)
    tblBorders = tblPr.find(qn("w:tblBorders"))
    if tblBorders is not None:
        tblPr.remove(tblBorders)
    tblBorders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "000000")
        tblBorders.append(e)
    tblPr.append(tblBorders)


def customize(doc: Document) -> None:
    """在 doc 的样式上就地修改教案风格。"""
    styles = doc.styles

    # 正文与派生样式（段落：宋体）
    for name, size in [
        ("Normal", 10.5),
        ("Body Text", 10.5),
        ("First Paragraph", 10.5),
        ("Compact", 10.5),
        ("Block Text", 10.5),
        ("Definition", 10.5),
        ("Definition Term", 10.5),
        ("Caption", 10),
        ("Table Caption", 10),
        ("Image Caption", 10),
        ("Figure", 10.5),
        ("Captioned Figure", 10.5),
        ("Footnote Text", 9),
        ("Footnote Block Text", 9),
    ]:
        if name in [s.name for s in styles]:
            style_normal(styles[name], pt_size=size)

    # 正文段落间距 + 行距 1.5
    set_paragraph_spacing(styles["Normal"], space_before_pt=0, space_after_pt=4, line_val=360, line_rule="auto")
    set_justification(styles["Normal"], val="both")

    # Title（封面大标题）
    style_heading(styles["Title"], pt_size=18, bold=True, color_hex="000000", sans=True)
    set_paragraph_spacing(styles["Title"], space_before_pt=12, space_after_pt=12, line_val=360)
    set_justification(styles["Title"], val="center")

    # Subtitle
    if "Subtitle" in [s.name for s in styles]:
        style_heading(styles["Subtitle"], pt_size=14, bold=False, color_hex="595959", sans=True)
        set_justification(styles["Subtitle"], val="center")

    # Heading 1-6（黑体黑色、取消 pandoc 默认蓝色）
    heading_sizes = {
        "Heading 1": 16,
        "Heading 2": 14,
        "Heading 3": 12,
        "Heading 4": 11,
        "Heading 5": 10.5,
        "Heading 6": 10.5,
    }
    for name, size in heading_sizes.items():
        if name in [s.name for s in styles]:
            style_heading(styles[name], pt_size=size, bold=True, color_hex="000000", sans=True)
            before, after = {
                "Heading 1": (12, 6),
                "Heading 2": (10, 6),
                "Heading 3": (8, 4),
                "Heading 4": (6, 3),
                "Heading 5": (6, 3),
                "Heading 6": (4, 2),
            }[name]
            set_paragraph_spacing(styles[name], space_before_pt=before, space_after_pt=after, line_val=320)

    # Heading N Char（行内版本的标题字符样式）同步修改
    for n in range(1, 7):
        cn = f"Heading {n} Char"
        if cn in [s.name for s in styles]:
            style_heading(styles[cn], pt_size=heading_sizes[f"Heading {n}"], bold=True, color_hex="000000", sans=True)

    # 代码相关
    if "Verbatim Char" in [s.name for s in styles]:
        style_mono(styles["Verbatim Char"], pt_size=9.5)
    if "Source Code" in [s.name for s in styles]:
        style_mono(styles["Source Code"], pt_size=9)

    # 超链接：保留蓝色下划线（保持通用样式）

    # Author / Date / Abstract 等元数据样式用正文字体
    for name in ["Author", "Date", "Abstract", "Abstract Title"]:
        if name in [s.name for s in styles]:
            style_normal(styles[name], pt_size=10.5)

    # Table 样式：添加全边框（pandoc 默认只在 header 下一道线）
    if "Table" in [s.name for s in styles]:
        set_table_borders(styles["Table"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_ref", help="输入的 pandoc 默认 reference.docx")
    ap.add_argument("output_ref", help="输出的定制模板 docx")
    args = ap.parse_args()

    inp = Path(args.input_ref).resolve()
    out = Path(args.output_ref).resolve()
    if not inp.is_file():
        print(f"ERROR: 输入文件不存在: {inp}", file=sys.stderr)
        sys.exit(1)

    doc = Document(inp)
    customize(doc)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
