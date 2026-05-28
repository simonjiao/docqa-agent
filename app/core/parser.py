from __future__ import annotations
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import os

import fitz

from .chunker import build_chunks
from .ocr import DEFAULT_DPI, render_page, ocr_image
from .pdf_probe import probe_pdf
from .schemas import BlockArtifact, EdgeArtifact, ElementArtifact, PageArtifact
from .storage import doc_dir, load_document, save_document
from .validators import recognition_checks


def process_pdf(doc_id: str, pdf_path: Path) -> Dict:
    if os.getenv("FORCE_REPROCESS", "0") != "1" and (doc_dir(doc_id) / "manifest.json").exists():
        return load_document(doc_id)

    probe = probe_pdf(pdf_path)
    root = doc_dir(doc_id)
    if probe.permission.get("action") == "request_password":
        protected_element = ElementArtifact(
            element_id="doc-e0001",
            doc_id=doc_id,
            element_type="unsupported_element",
            source_type="protected_pdf",
            text="PDF requires a password before parsing.",
            quality={"status": "blocked", "signals": ["blocked_by_permission"]},
        )
        elements = [
            protected_element
        ]
        edges = [
            EdgeArtifact(
                edge_id="edge-000001",
                from_id=protected_element.element_id,
                to_id=protected_element.element_id,
                edge_type="blocked_by_permission",
                rule_id="permission.v1.request_password",
                evidence=probe.permission,
                confidence=1.0,
            )
        ]
        manifest = _manifest(doc_id, pdf_path, probe.to_dict(), [], [])
        _write_markdown(root, manifest, [])
        save_document(doc_id, manifest, [], elements, edges, [], [])
        return load_document(doc_id)

    image_dir = root / "images"
    doc = fitz.open(pdf_path)

    pages: List[PageArtifact] = []
    elements: List[ElementArtifact] = []
    edges: List[EdgeArtifact] = []
    blocks: List[BlockArtifact] = []

    def add_edge(
        from_id: str,
        to_id: str,
        edge_type: str,
        rule_id: str,
        evidence: Dict[str, Any],
        confidence: float = 1.0,
    ) -> None:
        edges.append(
            EdgeArtifact(
                edge_id=f"edge-{len(edges) + 1:06d}",
                from_id=from_id,
                to_id=to_id,
                edge_type=edge_type,
                rule_id=rule_id,
                evidence=evidence,
                confidence=round(confidence, 4),
            )
        )

    metadata_id = "doc-e0001"
    elements.append(
        ElementArtifact(
            element_id=metadata_id,
            doc_id=doc_id,
            element_type="metadata",
            source_type="pdf_metadata",
            text=str(doc.metadata or {}),
            extractor={"name": "pymupdf"},
            quality={"status": "info", "signals": []},
        )
    )

    _extract_document_level_elements(doc, doc_id, elements, add_edge)

    for page_index in range(probe.pages):
        page_no = page_index + 1
        page_id = f"p{page_no:04d}"
        page = doc.load_page(page_index)
        image_path = image_dir / f"page-{page_no:04d}.png"
        image_width, image_height = render_page(pdf_path, page_index, image_path)
        recognition = ocr_image(image_path, page_no=page_no)
        checks = recognition_checks(recognition.to_dict())
        page_text_chars = len((page.get_text("text") or "").strip())
        page_image_blocks = _count_image_blocks(page)
        page_type = _classify_page(page_text_chars, page_image_blocks, recognition.text)

        page_artifact = PageArtifact(
            page_id=page_id,
            page_no=page_no,
            width=image_width,
            height=image_height,
            image_path=str(image_path.relative_to(root)),
            page_type=page_type,
            strategy=_page_strategy(page_type),
            text_layer_chars=page_text_chars,
            ocr_chars=len(recognition.text.strip()),
            image_blocks=page_image_blocks,
            table_region_count=len(recognition.table_regions),
            average_ocr_confidence=recognition.average_confidence,
            warnings=_page_warnings(page_type, recognition.average_confidence),
            checks=checks,
        )
        pages.append(page_artifact)

        page_element_id = f"{page_id}-e0001"
        page_render_id = f"{page_id}-e0002"
        elements.append(
            ElementArtifact(
                element_id=page_element_id,
                doc_id=doc_id,
                element_type="page",
                source_type="pdf_page",
                page_id=page_id,
                page_no=page_no,
                bbox=[0, 0, image_width, image_height],
                links={"image_path": str(image_path.relative_to(root))},
                extractor={"name": "pymupdf"},
            )
        )
        elements.append(
            ElementArtifact(
                element_id=page_render_id,
                doc_id=doc_id,
                element_type="page_render",
                source_type="page_render",
                page_id=page_id,
                page_no=page_no,
                bbox=[0, 0, image_width, image_height],
                links={"image_path": str(image_path.relative_to(root))},
                extractor={"name": "pymupdf", "dpi": DEFAULT_DPI},
            )
        )
        add_edge(page_element_id, page_render_id, "renders_to", "render_page.v1", {"page_id": page_id, "dpi": DEFAULT_DPI})

        page_elements = _extract_page_elements(page, doc_id, page_id, page_no, image_width, image_height, len(elements) + 1)
        for item in page_elements:
            elements.append(item)
            add_edge(
                page_element_id,
                item.element_id,
                "contains",
                "pdf_page_contains.v1",
                {"page_id": page_id, "element_type": item.element_type},
            )

        table_elements = _table_elements(
            doc_id,
            page_id,
            page_no,
            recognition.table_regions,
            start_index=len(elements) + 1,
        )
        for item in table_elements:
            elements.append(item)
            add_edge(page_element_id, item.element_id, "contains", "table_detection.v1", {"page_id": page_id})
            add_edge(page_render_id, item.element_id, "cropped_from", "table_detection.v1", {"bbox": item.bbox or []})

        ocr_elements = _ocr_elements(
            doc_id,
            page_id,
            page_no,
            recognition,
            start_index=len(elements) + 1,
        )
        for item in ocr_elements:
            elements.append(item)
            add_edge(page_element_id, item.element_id, "contains", "ocr_page_contains.v1", {"page_id": page_id})
            add_edge(
                page_render_id,
                item.element_id,
                "ocr_derived_from",
                "ocr.tesseract.page_line.v1",
                {"bbox": item.bbox or [], "confidence": item.confidence},
                confidence=float(item.confidence or 0) / 100 if item.confidence and item.confidence > 1 else float(item.confidence or 0),
            )

        _link_text_candidates(page_elements, ocr_elements, add_edge)

        primary_text = _primary_text_elements(page_elements, ocr_elements)
        page_blocks = _build_blocks_from_elements(doc_id, page_id, page_no, primary_text, start_index=len(blocks) + 1)
        for block in page_blocks:
            blocks.append(block)
            for element_id in block.element_ids:
                add_edge(
                    element_id,
                    block.block_id,
                    "contributes_to_block",
                    "block_builder.v1.reading_order_merge",
                    {"page_id": page_id, "block_id": block.block_id},
                )

    chunks, chunk_edges = build_chunks(doc_id, blocks)
    edges.extend(_renumber_edges(chunk_edges, start=len(edges) + 1))

    manifest = _manifest(doc_id, pdf_path, probe.to_dict(), pages, chunks)
    _write_markdown(root, manifest, chunks)
    save_document(doc_id, manifest, pages, elements, edges, blocks, chunks)
    return load_document(doc_id)


def _manifest(doc_id: str, pdf_path: Path, probe: Dict[str, Any], pages: List[PageArtifact], chunks: List[Any]) -> Dict[str, Any]:
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    return {
        "schema_version": "parse-artifact-v1",
        "doc_id": doc_id,
        "source_filename": pdf_path.name,
        "source_sha256": digest,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "parser": {"name": "docqa_agent_prototype", "version": "0.2.0"},
        "probe": probe,
        "page_count": len(pages),
        "chunk_count": len(chunks),
        "outputs": {
            "manifest": "manifest.json",
            "pages": "pages.jsonl",
            "elements": "elements.jsonl",
            "edges": "edges.jsonl",
            "blocks": "blocks.jsonl",
            "chunks": "chunks.jsonl",
            "markdown": "derived/full.md",
            "reviews": "reviews.jsonl",
        },
    }


def _write_markdown(root: Path, manifest: Dict[str, Any], chunks: List[Any]) -> None:
    path = root / "derived" / "full.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"<!-- doc_id: {manifest['doc_id']} -->",
        "<!-- generated_from: elements.jsonl edges.jsonl blocks.jsonl chunks.jsonl -->",
        "",
        "# Parsed Document",
        "",
    ]
    for chunk in chunks:
        source_blocks = ",".join(chunk.source_block_ids)
        source_types = ",".join(chunk.source_types)
        lines.extend(
            [
                f"<!-- chunk_id: {chunk.id} page: {chunk.page} blocks: {source_blocks} source_types: {source_types} -->",
                chunk.text,
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _extract_document_level_elements(doc: fitz.Document, doc_id: str, elements: List[ElementArtifact], add_edge: Any) -> None:
    try:
        emb_count = doc.embfile_count()
    except Exception:
        emb_count = 0
    for idx in range(emb_count):
        element_id = f"doc-e{len(elements) + 1:04d}"
        try:
            info = doc.embfile_info(idx)
            text = str(info)
            element_type = "attachment"
        except Exception:
            text = "embedded file could not be inspected"
            element_type = "unsupported_element"
        elements.append(
            ElementArtifact(
                element_id=element_id,
                doc_id=doc_id,
                element_type=element_type,
                source_type="pdf_attachment",
                text=text,
                extractor={"name": "pymupdf"},
            )
        )


def _extract_page_elements(
    page: fitz.Page,
    doc_id: str,
    page_id: str,
    page_no: int,
    image_width: int,
    image_height: int,
    start_index: int,
) -> List[ElementArtifact]:
    elements: List[ElementArtifact] = []
    seq = start_index

    for block in page.get_text("dict").get("blocks", []):
        block_type = block.get("type")
        if block_type == 0:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = (span.get("text") or "").strip()
                    if not text:
                        continue
                    bbox = _scale_bbox(span.get("bbox", [0, 0, 0, 0]), page.rect.width, page.rect.height, image_width, image_height)
                    elements.append(
                        ElementArtifact(
                            element_id=f"{page_id}-e{seq:04d}",
                            doc_id=doc_id,
                            element_type="text_span",
                            source_type="visible_text",
                            page_id=page_id,
                            page_no=page_no,
                            text=text,
                            bbox=bbox,
                            reading_order=seq,
                            raw_ref={"block_no": block.get("number")},
                            extractor={"name": "pymupdf.get_text.dict"},
                            quality={"status": "pass", "signals": []},
                        )
                    )
                    seq += 1
        elif block_type == 1:
            bbox = _scale_bbox(block.get("bbox", [0, 0, 0, 0]), page.rect.width, page.rect.height, image_width, image_height)
            elements.append(
                ElementArtifact(
                    element_id=f"{page_id}-e{seq:04d}",
                    doc_id=doc_id,
                    element_type="image_object",
                    source_type="image",
                    page_id=page_id,
                    page_no=page_no,
                    bbox=bbox,
                    reading_order=seq,
                    raw_ref={"block_no": block.get("number"), "ext": block.get("ext")},
                    extractor={"name": "pymupdf.get_text.dict"},
                    quality={"status": "info", "signals": ["image_object"]},
                )
            )
            seq += 1

    for drawing in _safe_drawings(page):
        rect = drawing.get("rect")
        if rect is None:
            continue
        bbox = _scale_bbox([rect.x0, rect.y0, rect.x1, rect.y1], page.rect.width, page.rect.height, image_width, image_height)
        elements.append(
            ElementArtifact(
                element_id=f"{page_id}-e{seq:04d}",
                doc_id=doc_id,
                element_type="vector_path",
                source_type="drawing_element",
                page_id=page_id,
                page_no=page_no,
                bbox=bbox,
                reading_order=seq,
                raw_ref={"items": len(drawing.get("items", []))},
                extractor={"name": "pymupdf.get_drawings"},
                quality={"status": "info", "signals": ["needs_specialized_parser"]},
            )
        )
        seq += 1

    for link in page.get_links():
        rect = link.get("from")
        bbox = None
        if rect is not None:
            bbox = _scale_bbox([rect.x0, rect.y0, rect.x1, rect.y1], page.rect.width, page.rect.height, image_width, image_height)
        elements.append(
            ElementArtifact(
                element_id=f"{page_id}-e{seq:04d}",
                doc_id=doc_id,
                element_type="link",
                source_type="pdf_link",
                page_id=page_id,
                page_no=page_no,
                bbox=bbox,
                reading_order=seq,
                raw_ref={k: str(v) for k, v in link.items() if k != "from"},
                extractor={"name": "pymupdf.get_links"},
            )
        )
        seq += 1

    try:
        widgets = page.widgets() or []
    except Exception:
        widgets = []
    for widget in widgets:
        rect = getattr(widget, "rect", None)
        bbox = None
        if rect is not None:
            bbox = _scale_bbox([rect.x0, rect.y0, rect.x1, rect.y1], page.rect.width, page.rect.height, image_width, image_height)
        elements.append(
            ElementArtifact(
                element_id=f"{page_id}-e{seq:04d}",
                doc_id=doc_id,
                element_type="form_field",
                source_type="form_field",
                page_id=page_id,
                page_no=page_no,
                text=str(getattr(widget, "field_value", "") or ""),
                bbox=bbox,
                reading_order=seq,
                raw_ref={"field_name": getattr(widget, "field_name", "")},
                extractor={"name": "pymupdf.widgets"},
            )
        )
        seq += 1

    annots = page.annots()
    if annots:
        for annot in annots:
            rect = annot.rect
            bbox = _scale_bbox([rect.x0, rect.y0, rect.x1, rect.y1], page.rect.width, page.rect.height, image_width, image_height)
            elements.append(
                ElementArtifact(
                    element_id=f"{page_id}-e{seq:04d}",
                    doc_id=doc_id,
                    element_type="annotation",
                    source_type="annotation",
                    page_id=page_id,
                    page_no=page_no,
                    text=str(annot.info or {}),
                    bbox=bbox,
                    reading_order=seq,
                    extractor={"name": "pymupdf.annots"},
                )
            )
            seq += 1

    return elements


def _ocr_elements(
    doc_id: str,
    page_id: str,
    page_no: int,
    recognition: Any,
    start_index: int,
) -> List[ElementArtifact]:
    result = []
    for offset, line in enumerate(recognition.lines):
        confidence = float(line.confidence)
        result.append(
            ElementArtifact(
                element_id=f"{page_id}-e{start_index + offset:04d}",
                doc_id=doc_id,
                element_type="ocr_text",
                source_type="image_ocr",
                page_id=page_id,
                page_no=page_no,
                text=line.text,
                bbox=line.bbox,
                reading_order=start_index + offset,
                confidence=confidence,
                source_group_id=f"{page_id}-g{start_index + offset:04d}",
                raw_ref={"ocr_line_id": line.id},
                extractor={"name": "tesseract"},
                quality={"status": "pass" if confidence >= 55 else "warn", "signals": [] if confidence >= 55 else ["low_ocr_confidence"]},
            )
        )
    return result


def _table_elements(
    doc_id: str,
    page_id: str,
    page_no: int,
    table_regions: List[Dict[str, Any]],
    start_index: int,
) -> List[ElementArtifact]:
    result = []
    for offset, table in enumerate(table_regions):
        result.append(
            ElementArtifact(
                element_id=f"{page_id}-e{start_index + offset:04d}",
                doc_id=doc_id,
                element_type="table_region",
                source_type="table_detection",
                page_id=page_id,
                page_no=page_no,
                bbox=table.get("bbox", []),
                reading_order=start_index + offset,
                raw_ref={"table_id": table.get("id"), "reason": table.get("reason")},
                extractor={"name": "opencv.table_region"},
                quality={"status": "info", "signals": ["needs_specialized_parser"]},
            )
        )
    return result


def _build_blocks_from_elements(
    doc_id: str,
    page_id: str,
    page_no: int,
    text_elements: List[ElementArtifact],
    start_index: int,
) -> List[BlockArtifact]:
    blocks = []
    for offset, element in enumerate(text_elements):
        if not element.text.strip():
            continue
        bbox = element.bbox or [0, 0, 0, 0]
        blocks.append(
            BlockArtifact(
                block_id=f"{page_id}-b{start_index + offset:04d}",
                doc_id=doc_id,
                page_id=page_id,
                page_no=page_no,
                text=element.text,
                element_ids=[element.element_id],
                source_types=[element.source_type],
                source_group_ids=[element.source_group_id] if element.source_group_id else [],
                bbox=bbox,
                kind="table" if "表" in element.text or "AQL" in element.text or "检查项目" in element.text else "text",
                confidence=float(element.confidence or 1.0),
                warnings=element.quality.get("signals", []),
            )
        )
    return blocks


def _primary_text_elements(page_elements: List[ElementArtifact], ocr_elements: List[ElementArtifact]) -> List[ElementArtifact]:
    visible_text = [item for item in page_elements if item.element_type == "text_span" and item.text.strip()]
    visible_chars = sum(len(item.text.strip()) for item in visible_text)
    if visible_chars >= 80:
        return sorted(visible_text, key=lambda item: item.reading_order)
    return sorted(ocr_elements, key=lambda item: item.reading_order)


def _link_text_candidates(page_elements: List[ElementArtifact], ocr_elements: List[ElementArtifact], add_edge: Any) -> None:
    text_elements = [item for item in page_elements if item.element_type in {"text_span", "hidden_text_span"} and item.bbox and item.text]
    for text_element in text_elements:
        best: Optional[Tuple[ElementArtifact, float]] = None
        for ocr_element in ocr_elements:
            overlap = _bbox_overlap(text_element.bbox or [], ocr_element.bbox or [])
            if overlap > 0.5 and (best is None or overlap > best[1]):
                best = (ocr_element, overlap)
        if best is None:
            continue
        ocr_element, overlap = best
        group_id = ocr_element.source_group_id or f"{ocr_element.page_id}-g{ocr_element.element_id.rsplit('e', 1)[-1]}"
        text_element.source_group_id = group_id
        similarity = SequenceMatcher(None, _normalize_text(text_element.text), _normalize_text(ocr_element.text)).ratio()
        add_edge(
            text_element.element_id,
            ocr_element.element_id,
            "text_candidate_for",
            "text_candidate.v1.bbox_overlap",
            {"bbox_overlap": overlap, "text_similarity": similarity, "source_group_id": group_id},
            confidence=overlap,
        )
        if similarity >= 0.75:
            add_edge(
                text_element.element_id,
                ocr_element.element_id,
                "equivalent_to",
                "text_equivalence.v1.bbox_and_similarity",
                {"bbox_overlap": overlap, "text_similarity": similarity, "source_group_id": group_id},
                confidence=similarity,
            )
            add_edge(
                text_element.element_id,
                ocr_element.element_id,
                "chosen_over",
                "text_choice.v1.visible_text_preferred",
                {"reason": "usable_visible_text_layer", "source_group_id": group_id},
                confidence=0.9,
            )
        else:
            add_edge(
                text_element.element_id,
                ocr_element.element_id,
                "conflicts_with",
                "text_conflict.v1.bbox_without_similarity",
                {"bbox_overlap": overlap, "text_similarity": similarity, "source_group_id": group_id},
                confidence=1 - similarity,
            )


def _renumber_edges(edges: List[EdgeArtifact], start: int) -> List[EdgeArtifact]:
    result = []
    for offset, edge in enumerate(edges):
        edge.edge_id = f"edge-{start + offset:06d}"
        result.append(edge)
    return result


def _classify_page(text_chars: int, image_blocks: int, ocr_text: str) -> str:
    if text_chars >= 80 and image_blocks:
        return "ocr_page"
    if text_chars >= 80:
        return "text_page"
    if ocr_text.strip():
        return "scan_page"
    return "mixed_page"


def _page_strategy(page_type: str) -> str:
    return {
        "ocr_page": "hidden_text_quality_check_plus_region_ocr",
        "text_page": "extract_text_elements",
        "scan_page": "render_page_then_ocr",
        "mixed_page": "mixed_element_extraction",
    }.get(page_type, "mixed_element_extraction")


def _page_warnings(page_type: str, average_confidence: float) -> List[str]:
    warnings = []
    if page_type == "ocr_page":
        warnings.append("hidden_text_needs_quality_check")
    if average_confidence < 55:
        warnings.append("low_ocr_confidence")
    return warnings


def _count_image_blocks(page: fitz.Page) -> int:
    return sum(1 for block in page.get_text("dict").get("blocks", []) if block.get("type") == 1)


def _safe_drawings(page: fitz.Page) -> List[Dict[str, Any]]:
    try:
        return page.get_drawings()
    except Exception:
        return []


def _scale_bbox(bbox: List[float], pdf_width: float, pdf_height: float, image_width: int, image_height: int) -> List[int]:
    x0, y0, x1, y1 = bbox
    scale_x = image_width / max(1.0, float(pdf_width))
    scale_y = image_height / max(1.0, float(pdf_height))
    return [
        int(round(x0 * scale_x)),
        int(round(y0 * scale_y)),
        int(round((x1 - x0) * scale_x)),
        int(round((y1 - y0) * scale_y)),
    ]


def _bbox_overlap(a: List[int], b: List[int]) -> float:
    if len(a) != 4 or len(b) != 4:
        return 0.0
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    smaller = max(1, min(aw * ah, bw * bh))
    return intersection / smaller


def _normalize_text(text: str) -> str:
    return "".join(ch.lower() for ch in text if not ch.isspace())
