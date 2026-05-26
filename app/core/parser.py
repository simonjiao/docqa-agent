from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import fitz

from .chunker import build_chunks
from .ocr import render_page, ocr_image
from .pdf_probe import probe_pdf
from .schemas import Chunk, PageRecognition
from .storage import doc_dir, save_document
from .validators import recognition_checks


def process_pdf(doc_id: str, pdf_path: Path) -> Dict:
    # Avoid repeating OCR when the same document has already been processed.
    # Set FORCE_REPROCESS=1 to rebuild during debugging.
    import os
    from .storage import load_document
    if os.getenv("FORCE_REPROCESS", "0") != "1" and (doc_dir(doc_id) / "meta.json").exists():
        return load_document(doc_id)

    probe = probe_pdf(pdf_path)
    root = doc_dir(doc_id)
    image_dir = root / "pages"
    pages: List[PageRecognition] = []

    for page_index in range(probe.pages):
        image_path = image_dir / f"page-{page_index + 1}.png"
        render_page(pdf_path, page_index, image_path)
        recognition = ocr_image(image_path, page_no=page_index + 1)
        pages.append(recognition)

    chunks: List[Chunk] = build_chunks(doc_id, pages)
    meta = {
        "doc_id": doc_id,
        "source_filename": pdf_path.name,
        "probe": probe.to_dict(),
        "page_count": probe.pages,
        "chunk_count": len(chunks),
        "recognition_checks": {
            str(page.page): recognition_checks(page.to_dict()) for page in pages
        },
    }
    save_document(doc_id, meta, pages, chunks)
    return {"meta": meta, "pages": [p.to_dict() for p in pages], "chunks": [c.to_dict() for c in chunks]}
