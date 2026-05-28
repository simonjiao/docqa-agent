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
    vector_drawings = 0
    notes = []
    has_forms = False
    is_encrypted = bool(getattr(doc, "is_encrypted", False))
    permission = {
        "requires_password": bool(getattr(doc, "needs_pass", False)),
        "authenticated": not bool(getattr(doc, "needs_pass", False)),
        "allows_text_extraction": True,
        "allows_rendering": True,
        "action": "parse",
    }
    if permission["requires_password"]:
        return PdfProbeResult(
            pdf_type="protected_pdf",
            pages=doc.page_count,
            text_chars=0,
            image_blocks=0,
            strategy="request_password",
            notes=["PDF requires a password before parsing."],
            pdf_type_candidates=["protected_pdf"],
            has_text_layer=False,
            has_hidden_text=False,
            has_images=False,
            has_forms=False,
            has_vector_drawings=False,
            is_encrypted=is_encrypted,
            permission={**permission, "action": "request_password"},
        )

    for page in doc:
        extracted = page.get_text("text") or ""
        text_chars += len(extracted.strip())
        blocks = page.get_text("dict").get("blocks", [])
        image_blocks += sum(1 for block in blocks if block.get("type") == 1)
        try:
            vector_drawings += len(page.get_drawings())
        except Exception:
            pass
        try:
            widgets = list(page.widgets() or [])
            if widgets:
                has_forms = True
        except Exception:
            pass

    pages = doc.page_count
    avg_chars = text_chars / max(1, pages)
    has_text_layer = text_chars > 0
    has_images = image_blocks > 0
    has_vector_drawings = vector_drawings > 0
    has_hidden_text = has_text_layer and has_images
    candidates = []

    if has_forms:
        pdf_type = "form_pdf"
        strategy = "extract_form_fields_plus_page_elements"
        notes.append("PDF contains form widgets; extract fields and page elements.")
    elif avg_chars >= 30 and not has_images:
        pdf_type = "text_pdf"
        strategy = "extract_text_then_ocr_fallback"
        notes.append("PDF has a usable text layer; use text extraction first.")
        if has_vector_drawings:
            notes.append("PDF also has vector drawings; preserve them as secondary visual elements.")
    elif avg_chars >= 30 and has_images:
        pdf_type = "ocr_pdf"
        strategy = "hidden_text_quality_check_plus_region_ocr"
        notes.append("PDF has text and image signals; treat text layer as candidate and validate visually.")
    elif image_blocks > 0:
        pdf_type = "scan_pdf"
        strategy = "render_pages_then_ocr"
        notes.append("PDF has little/no text layer and image blocks; use OCR.")
    elif has_vector_drawings:
        pdf_type = "drawing_pdf"
        strategy = "extract_vector_elements_plus_visual_review"
        notes.append("PDF has vector drawings; preserve drawing elements and use visual review.")
    else:
        pdf_type = "mixed_pdf"
        strategy = "text_extraction_plus_page_level_ocr"
        notes.append("PDF signal is ambiguous; use mixed strategy and validate by page.")

    if pages == 0:
        notes.append("No pages detected; reject before OCR.")

    if has_text_layer:
        candidates.append("text_pdf")
    if has_images:
        candidates.append("scan_pdf")
    if has_hidden_text:
        candidates.append("ocr_pdf")
    if has_forms:
        candidates.append("form_pdf")
    if has_vector_drawings:
        candidates.append("drawing_pdf")
    if is_encrypted or permission["requires_password"]:
        candidates.append("protected_pdf")
    if not candidates:
        candidates.append("mixed_pdf")

    return PdfProbeResult(
        pdf_type=pdf_type,
        pages=pages,
        text_chars=text_chars,
        image_blocks=image_blocks,
        strategy=strategy,
        notes=notes,
        pdf_type_candidates=sorted(set(candidates)),
        has_text_layer=has_text_layer,
        has_hidden_text=has_hidden_text,
        has_images=has_images,
        has_forms=has_forms,
        has_vector_drawings=has_vector_drawings,
        is_encrypted=is_encrypted,
        permission=permission,
    )
