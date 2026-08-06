# /// script
# dependencies = ["PyMuPDF"]
# ///
"""将 PDF 前 N 页转为 PNG 缩略图，用于样例库审核。"""
import sys
from pathlib import Path
import fitz  # PyMuPDF


def pdf_to_images(pdf_path: Path, out_dir: Path, max_pages: int = 30, dpi: int = 120) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    total = min(len(doc), max_pages)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    written: list[Path] = []
    for i in range(total):
        page = doc[i]
        pix = page.get_pixmap(matrix=matrix)
        out = out_dir / f"p{i+1:03d}.png"
        pix.save(out)
        written.append(out)
    doc.close()
    return written


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: pdf_to_images.py <pdf> <out_dir> [max_pages] [dpi]")
        sys.exit(2)
    pdf = Path(sys.argv[1])
    out = Path(sys.argv[2])
    max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    dpi = int(sys.argv[4]) if len(sys.argv) > 4 else 120
    imgs = pdf_to_images(pdf, out, max_pages=max_pages, dpi=dpi)
    print(f"{pdf.name}: {len(imgs)} pages -> {out}")


if __name__ == "__main__":
    main()
