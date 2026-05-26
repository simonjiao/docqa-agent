from __future__ import annotations
from pathlib import Path
import fitz  # PyMuPDF
from .schemas import PdfProbeResult


def probe_pdf(pdf_path: Path) -> PdfProbeResult:
    """Classify PDF and decide parsing strategy.

    Rules are intentionally transparent for interview review:
    - text_layer_pdf: enough extractable text, prefer text extractor + layout parser.
    - scanned_pdf: almost no extractable text and image blocks exist, prefer rendering + OCR.
    - hybrid_pdf: use text extractor first and OCR fallback by page.
    """
    doc = fitz.open(pdf_path)
    text_chars = 0
    image_blocks = 0
    notes = []
    for page in doc:
        extracted = page.get_text("text") or ""
        text_chars += len(extracted.strip())
        blocks = page.get_text("dict").get("blocks", [])
        image_blocks += sum(1 for block in blocks if block.get("type") == 1)

    pages = doc.page_count
    avg_chars = text_chars / max(1, pages)

    if avg_chars >= 80:
        pdf_type = "text_layer_pdf"
        strategy = "extract_text_then_ocr_fallback"
        notes.append("PDF has a usable text layer; use text extraction first.")
    elif image_blocks > 0:
        pdf_type = "scanned_pdf"
        strategy = "render_pages_then_ocr"
        notes.append("PDF has little/no text layer and image blocks; use OCR.")
    else:
        pdf_type = "hybrid_or_unknown_pdf"
        strategy = "text_extraction_plus_page_level_ocr"
        notes.append("PDF signal is ambiguous; use mixed strategy and validate by page.")

    if pages == 0:
        notes.append("No pages detected; reject before OCR.")

    return PdfProbeResult(
        pdf_type=pdf_type,
        pages=pages,
        text_chars=text_chars,
        image_blocks=image_blocks,
        strategy=strategy,
        notes=notes,
    )
