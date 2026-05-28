from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import math
import re

import numpy as np
from PIL import Image
import pytesseract

from .ocr import DEFAULT_TIMEOUT, resolve_ocr_lang
from .schemas import BlockArtifact, EdgeArtifact, ElementArtifact, TableArtifact

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    cv2 = None


@dataclass
class TableParseResult:
    elements: List[ElementArtifact]
    edges: List[EdgeArtifact]
    blocks: List[BlockArtifact]
    tables: List[TableArtifact]


@dataclass
class _GridResult:
    strategy: str
    cells: List[List[Dict[str, Any]]]
    row_bboxes: List[List[int]]
    column_bboxes: List[List[int]]
    line_bboxes: List[List[int]]
    confidence: float
    warnings: List[str]


@dataclass
class _BorderlessLayout:
    rows: List[List["ElementArtifact"]]
    column_centers: List[int]
    row_bboxes: List[List[int]]
    diagnostics: Dict[str, Any]


@dataclass
class _CellText:
    text: str
    source_element_ids: List[str]
    candidate_element_ids: List[str]
    confidence: float
    warnings: List[str]
    used_cell_ocr: bool = False


def parse_tables(
    *,
    doc_id: str,
    page_id: str,
    page_no: int,
    image_path: Path,
    image_width: int,
    image_height: int,
    page_element_id: str,
    page_render_id: str,
    table_regions: List[ElementArtifact],
    text_candidates: List[ElementArtifact],
    start_element_index: int,
    start_block_index: int,
) -> TableParseResult:
    """Parse table structure while keeping elements/edges as the source of truth."""
    result = TableParseResult(elements=[], edges=[], blocks=[], tables=[])
    element_seq = start_element_index
    block_seq = start_block_index
    edge_seq = 1
    image = Image.open(image_path).convert("RGB")

    def next_element_id() -> str:
        nonlocal element_seq
        element_id = f"{page_id}-e{element_seq:04d}"
        element_seq += 1
        return element_id

    def next_block_id() -> str:
        nonlocal block_seq
        block_id = f"{page_id}-b{block_seq:04d}"
        block_seq += 1
        return block_id

    def add_edge(
        from_id: str,
        to_id: str,
        edge_type: str,
        rule_id: str,
        evidence: Dict[str, Any],
        confidence: float = 1.0,
    ) -> None:
        nonlocal edge_seq
        result.edges.append(
            EdgeArtifact(
                edge_id=f"edge-table-{edge_seq:06d}",
                from_id=from_id,
                to_id=to_id,
                edge_type=edge_type,
                rule_id=rule_id,
                evidence=evidence,
                confidence=round(confidence, 4),
            )
        )
        edge_seq += 1

    regions = list(table_regions)
    if not regions:
        visible_candidates = [item for item in text_candidates if item.source_type in {"visible_text", "hidden_text", "form_field"} and item.text.strip()]
        inferred = _infer_borderless_region(doc_id, page_id, page_no, visible_candidates or text_candidates, next_element_id)
        if inferred is not None:
            result.elements.append(inferred)
            regions.append(inferred)
            add_edge(page_element_id, inferred.element_id, "contains", "table_detection.v1.text_alignment", {"page_id": page_id})
            add_edge(page_render_id, inferred.element_id, "cropped_from", "table_detection.v1.text_alignment", {"bbox": inferred.bbox or []})

    for table_index, region in enumerate(regions, start=1):
        bbox = region.bbox or [0, 0, 0, 0]
        if not _valid_bbox(bbox):
            continue
        region_candidates = _elements_in_bbox(text_candidates, bbox, min_overlap=0.15)
        preferred_candidates = [item for item in region_candidates if item.source_type in {"visible_text", "hidden_text", "form_field"} and item.text.strip()]
        assignment_candidates = preferred_candidates or region_candidates
        grid = _parse_ruled_grid(image, bbox)
        if grid is None:
            grid = _parse_borderless_grid(bbox, assignment_candidates)
        if grid is None:
            structure_id = next_element_id()
            structure = ElementArtifact(
                element_id=structure_id,
                doc_id=doc_id,
                element_type="table_structure",
                source_type="table_detection",
                page_id=page_id,
                page_no=page_no,
                bbox=bbox,
                parent_element_id=region.element_id,
                raw_ref={"region_element_id": region.element_id, "status": "failed"},
                extractor={"name": "table_parser.v1"},
                quality={"status": "failed", "signals": ["table_structure_failed"]},
            )
            result.elements.append(structure)
            add_edge(page_element_id, structure_id, "contains", "table_parser.v1.page_contains_structure", {"page_id": page_id})
            add_edge(region.element_id, structure_id, "contains", "table_parser.v1.region_contains_structure", {"region_element_id": region.element_id})
            continue

        table_id = f"{page_id}-t{table_index:04d}"
        structure_id = next_element_id()
        has_visible_text = any(item.source_type == "visible_text" and item.text.strip() for item in region_candidates)
        strategy = "scanned_ocr_table" if not has_visible_text and grid.strategy == "ruled_grid" else grid.strategy
        structure = ElementArtifact(
            element_id=structure_id,
            doc_id=doc_id,
            element_type="table_structure",
            source_type="table_structure",
            page_id=page_id,
            page_no=page_no,
            bbox=bbox,
            parent_element_id=region.element_id,
            source_group_id=table_id,
            raw_ref={"table_id": table_id, "region_element_id": region.element_id, "strategy": strategy},
            extractor={"name": "table_parser.v1", "strategy": strategy},
            quality={"status": "info", "signals": []},
        )
        result.elements.append(structure)
        add_edge(page_element_id, structure_id, "contains", "table_parser.v1.page_contains_structure", {"page_id": page_id})
        add_edge(region.element_id, structure_id, "contains", "table_parser.v1.region_contains_structure", {"region_element_id": region.element_id})
        add_edge(page_render_id, structure_id, "cropped_from", "table_parser.v1.structure_from_render", {"bbox": bbox})

        line_ids = _add_line_elements(
            result=result,
            grid=grid,
            doc_id=doc_id,
            page_id=page_id,
            page_no=page_no,
            structure_id=structure_id,
            next_element_id=next_element_id,
            add_edge=add_edge,
        )
        row_ids = _add_axis_elements(
            result=result,
            axis="row",
            bboxes=grid.row_bboxes,
            doc_id=doc_id,
            page_id=page_id,
            page_no=page_no,
            structure_id=structure_id,
            next_element_id=next_element_id,
            add_edge=add_edge,
        )
        column_ids = _add_axis_elements(
            result=result,
            axis="column",
            bboxes=grid.column_bboxes,
            doc_id=doc_id,
            page_id=page_id,
            page_no=page_no,
            structure_id=structure_id,
            next_element_id=next_element_id,
            add_edge=add_edge,
        )

        cell_ids: List[str] = []
        cell_text_rows: List[List[str]] = []
        cell_warnings: List[str] = []
        cell_confidences: List[float] = []
        for row_index, row_cells in enumerate(grid.cells):
            text_row: List[str] = []
            row_assignments = _assign_candidates_to_cells(row_cells, assignment_candidates)
            for column_index, cell_info in enumerate(row_cells):
                cell_bbox = _cell_bbox(cell_info)
                cell_id = next_element_id()
                cell_text = _cell_text(
                    cell_bbox,
                    row_assignments.get(column_index, []),
                    image,
                    use_cell_ocr=(strategy == "scanned_ocr_table"),
                )
                final_text = cell_text.text
                warnings = sorted(set(cell_text.warnings))
                if cell_text.used_cell_ocr and cell_text.confidence < 55:
                    final_text = ""
                    warnings = sorted(set(warnings + ["low_cell_ocr_confidence", "needs_review"]))
                cell = ElementArtifact(
                    element_id=cell_id,
                    doc_id=doc_id,
                    element_type="table_cell",
                    source_type="table_cell",
                    page_id=page_id,
                    page_no=page_no,
                    text=final_text,
                    bbox=cell_bbox,
                    reading_order=row_index * max(1, len(row_cells)) + column_index,
                    confidence=round(cell_text.confidence, 3),
                    parent_element_id=structure_id,
                    source_group_id=table_id,
                    raw_ref={
                        "table_id": table_id,
                        "row_index": row_index,
                        "column_index": cell_info.get("column_index", column_index),
                        "row_span": cell_info.get("row_span", 1),
                        "col_span": cell_info.get("col_span", 1),
                    },
                    extractor={"name": "table_parser.v1", "strategy": strategy},
                    quality={"status": "needs_review" if "needs_review" in warnings else "pass", "signals": warnings},
                )
                result.elements.append(cell)
                cell_ids.append(cell_id)
                text_row.append(final_text)
                cell_warnings.extend(warnings)
                cell_confidences.append(cell_text.confidence)
                add_edge(structure_id, cell_id, "contains", "table_parser.v1.structure_contains_cell", {"table_id": table_id})
                if row_index < len(row_ids):
                    add_edge(row_ids[row_index], cell_id, "cell_in_row", "table_parser.v1.row_membership", {"row_index": row_index})
                if column_index < len(column_ids):
                    add_edge(column_ids[column_index], cell_id, "cell_in_column", "table_parser.v1.column_membership", {"column_index": column_index})
                for line_id in line_ids:
                    add_edge(line_id, cell_id, "table_boundary_from_line", "table_parser.v1.boundary_line", {"table_id": table_id}, confidence=0.35)
                for source_id in cell_text.candidate_element_ids:
                    add_edge(source_id, cell_id, "text_candidate_for", "table_parser.v1.cell_text_candidate", {"table_id": table_id, "cell_id": cell_id})
                for source_id in cell_text.source_element_ids:
                    add_edge(source_id, cell_id, "chosen_over", "table_parser.v1.cell_text_choice", {"table_id": table_id, "cell_id": cell_id})

                if cell_text.used_cell_ocr:
                    ocr_element_id = next_element_id()
                    ocr_element = ElementArtifact(
                        element_id=ocr_element_id,
                        doc_id=doc_id,
                        element_type="ocr_text",
                        source_type="cell_ocr",
                        page_id=page_id,
                        page_no=page_no,
                        text=cell_text.text,
                        bbox=cell_bbox,
                        confidence=round(cell_text.confidence, 3),
                        parent_element_id=cell_id,
                        source_group_id=f"{table_id}-r{row_index:03d}c{column_index:03d}",
                        raw_ref={"table_id": table_id, "cell_id": cell_id},
                        extractor={"name": "tesseract", "scope": "table_cell"},
                        quality={"status": "warn" if cell_text.confidence < 55 else "pass", "signals": ["low_ocr_confidence"] if cell_text.confidence < 55 else []},
                    )
                    result.elements.append(ocr_element)
                    add_edge(cell_id, ocr_element_id, "ocr_derived_from", "table_parser.v1.cell_ocr", {"table_id": table_id, "bbox": cell_bbox}, confidence=max(0.0, min(1.0, cell_text.confidence / 100)))
                    add_edge(ocr_element_id, cell_id, "text_candidate_for", "table_parser.v1.cell_ocr_candidate", {"table_id": table_id, "cell_id": cell_id})
            cell_text_rows.append(text_row)

        table = _table_artifact(
            table_id=table_id,
            doc_id=doc_id,
            page_id=page_id,
            page_no=page_no,
            region_element_id=region.element_id,
            structure_element_id=structure_id,
            strategy=strategy,
            bbox=bbox,
            rows=cell_text_rows,
            cell_ids=cell_ids,
            base_confidence=grid.confidence,
            cell_confidences=cell_confidences,
            warnings=sorted(set(grid.warnings + cell_warnings + (["needs_review", "scanned_table_needs_review"] if strategy == "scanned_ocr_table" else []))),
        )
        status = table.status
        structure.quality = {"status": status, "signals": table.warnings}
        structure.confidence = table.confidence
        result.tables.append(table)

        table_blocks = _table_blocks(
            doc_id=doc_id,
            page_id=page_id,
            page_no=page_no,
            table=table,
            structure_id=structure_id,
            cell_ids=cell_ids,
            next_block_id=next_block_id,
        )
        for block in table_blocks:
            result.blocks.append(block)
            add_edge(structure_id, block.block_id, "contributes_to_block", "table_block_builder.v1.structure", {"table_id": table_id, "block_id": block.block_id})
            for cell_id in cell_ids:
                add_edge(cell_id, block.block_id, "contributes_to_block", "table_block_builder.v1.cell", {"table_id": table_id, "block_id": block.block_id}, confidence=0.9)

    return result


def _parse_ruled_grid(image: Image.Image, bbox: List[int]) -> Optional[_GridResult]:
    if cv2 is None:
        return None
    x, y, w, h = bbox
    crop = image.crop((x, y, x + w, y + h)).convert("L")
    arr = np.array(crop)
    if arr.size == 0:
        return None
    binary = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 35, 15)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(18, w // 10), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(18, h // 8)))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=1)

    ys, horizontal_lines = _line_positions(horizontal, "horizontal", bbox)
    xs, vertical_lines = _line_positions(vertical, "vertical", bbox)
    if len(horizontal_lines) < 2 or len(vertical_lines) < 2:
        return None
    xs = _merge_positions([0, w] + [pos - x for pos in xs], tolerance=8)
    ys = _merge_positions([0, h] + [pos - y for pos in ys], tolerance=8)
    if len(xs) < 2 or len(ys) < 2:
        return None
    xs = [max(0, min(w, item)) for item in xs]
    ys = [max(0, min(h, item)) for item in ys]
    xs = sorted(set(xs))
    ys = sorted(set(ys))
    if len(xs) < 2 or len(ys) < 2:
        return None

    cells: List[List[Dict[str, Any]]] = []
    for row_idx in range(len(ys) - 1):
        row_top, row_bottom = y + ys[row_idx], y + ys[row_idx + 1]
        row_boundaries = [{"x": 0, "global_index": 0}]
        for col_idx, boundary in enumerate(xs[1:-1], start=1):
            if _vertical_boundary_present(x + boundary, row_top, row_bottom, vertical_lines):
                row_boundaries.append({"x": boundary, "global_index": col_idx})
        row_boundaries.append({"x": w, "global_index": len(xs) - 1})
        row_boundaries = sorted(row_boundaries, key=lambda item: item["x"])
        row = []
        for left_boundary, right_boundary in zip(row_boundaries, row_boundaries[1:]):
            left, right = x + left_boundary["x"], x + right_boundary["x"]
            top, bottom = row_top, row_bottom
            if right - left < 8 or bottom - top < 8:
                continue
            row.append(
                {
                    "bbox": [left, top, right - left, bottom - top],
                    "row_index": row_idx,
                    "column_index": left_boundary["global_index"],
                    "row_span": 1,
                    "col_span": max(1, right_boundary["global_index"] - left_boundary["global_index"]),
                }
            )
        if row:
            cells.append(row)
    if not cells:
        return None
    line_bboxes = horizontal_lines + vertical_lines
    confidence = min(0.98, 0.45 + 0.04 * len(line_bboxes) + 0.02 * sum(len(row) for row in cells))
    return _GridResult(
        strategy="ruled_grid",
        cells=cells,
        row_bboxes=[_union_bbox([_cell_bbox(cell) for cell in row]) for row in cells],
        column_bboxes=[[x + xs[idx], y, xs[idx + 1] - xs[idx], h] for idx in range(len(xs) - 1)],
        line_bboxes=line_bboxes,
        confidence=round(confidence, 3),
        warnings=[],
    )


def _parse_borderless_grid(region_bbox: List[int], candidates: List[ElementArtifact]) -> Optional[_GridResult]:
    layout = _borderless_layout(candidates)
    if layout is None:
        return None
    rows = layout.rows
    column_centers = layout.column_centers
    x, y, w, h = region_bbox
    boundaries = [x]
    for left, right in zip(column_centers, column_centers[1:]):
        boundaries.append(int(round((left + right) / 2)))
    boundaries.append(x + w)
    boundaries = sorted(set(boundaries))
    if len(boundaries) < 3:
        return None

    row_bboxes = layout.row_bboxes
    row_tops = [bbox[1] for bbox in row_bboxes]
    row_bottoms = [bbox[1] + bbox[3] for bbox in row_bboxes]
    y_boundaries = [max(y, row_tops[0] - 6)]
    for prev_bottom, next_top in zip(row_bottoms, row_tops[1:]):
        y_boundaries.append(int(round((prev_bottom + next_top) / 2)))
    y_boundaries.append(min(y + h, row_bottoms[-1] + 6))

    cells: List[List[Dict[str, Any]]] = []
    for row_idx in range(len(y_boundaries) - 1):
        row = []
        for col_idx in range(len(boundaries) - 1):
            row.append(
                {
                    "bbox": [boundaries[col_idx], y_boundaries[row_idx], boundaries[col_idx + 1] - boundaries[col_idx], y_boundaries[row_idx + 1] - y_boundaries[row_idx]],
                    "row_index": row_idx,
                    "column_index": col_idx,
                    "row_span": 1,
                    "col_span": 1,
                }
            )
        cells.append(row)
    warnings = []
    expected = len(cells[0]) if cells else 0
    if any(len(row) != expected for row in cells):
        warnings.append("unstable_column_count")
    confidence = 0.72 if not warnings else 0.58
    return _GridResult(
        strategy="borderless_alignment",
        cells=cells,
        row_bboxes=[_union_bbox([_cell_bbox(cell) for cell in row]) for row in cells],
        column_bboxes=[_union_bbox([_cell_bbox(row[idx]) for row in cells if idx < len(row)]) for idx in range(max(len(row) for row in cells))],
        line_bboxes=[],
        confidence=confidence,
        warnings=warnings,
    )


def _line_positions(mask: Any, orientation: str, table_bbox: List[int]) -> Tuple[List[int], List[List[int]]]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)  # type: ignore[union-attr]
    tx, ty, tw, th = table_bbox
    positions: List[int] = []
    bboxes: List[List[int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)  # type: ignore[union-attr]
        if orientation == "horizontal":
            if w < tw * 0.25:
                continue
            positions.append(ty + y + h // 2)
        else:
            if h < th * 0.25:
                continue
            positions.append(tx + x + w // 2)
        bboxes.append([tx + int(x), ty + int(y), int(w), int(h)])
    return sorted(positions), bboxes


def _vertical_boundary_present(abs_x: int, row_top: int, row_bottom: int, vertical_lines: List[List[int]]) -> bool:
    row_height = max(1, row_bottom - row_top)
    for line in vertical_lines:
        if not _valid_bbox(line):
            continue
        line_center = line[0] + line[2] / 2
        if abs(line_center - abs_x) > max(6, line[2] + 3):
            continue
        overlap = _axis_overlap(row_top, row_bottom, line[1], line[1] + line[3])
        if overlap / row_height >= 0.45:
            return True
    return False


def _assign_candidates_to_cells(cells: List[Dict[str, Any]], candidates: List[ElementArtifact]) -> Dict[int, List[ElementArtifact]]:
    assignments: Dict[int, List[ElementArtifact]] = {idx: [] for idx in range(len(cells))}
    for candidate in candidates:
        candidate_bbox = candidate.bbox or []
        if not _valid_bbox(candidate_bbox):
            continue
        best_idx: Optional[int] = None
        best_score = 0.0
        center = _bbox_center(candidate_bbox)
        for idx, cell in enumerate(cells):
            bbox = _cell_bbox(cell)
            score = _bbox_overlap_candidate_ratio(candidate_bbox, bbox)
            if _point_in_bbox(center, bbox):
                score += 2.0
            if score > best_score:
                best_idx = idx
                best_score = score
        if best_idx is not None and best_score > 0.01:
            assignments[best_idx].append(candidate)
    return assignments


def _cell_text(cell_bbox: List[int], candidates: List[ElementArtifact], image: Image.Image, use_cell_ocr: bool) -> _CellText:
    assigned = _elements_in_bbox(candidates, cell_bbox, min_overlap=0.05)
    assigned = sorted(assigned, key=lambda item: ((item.bbox or [0, 0, 0, 0])[1], (item.bbox or [0, 0, 0, 0])[0], item.reading_order))
    text = _merge_candidate_text(assigned)
    confidence = _candidate_confidence(assigned)
    warnings = ["low_candidate_confidence"] if assigned and confidence < 55 else []
    if use_cell_ocr and _valid_bbox(cell_bbox):
        ocr_text, ocr_conf = _ocr_cell(image, cell_bbox)
        warnings = ["low_cell_ocr_confidence"] if ocr_conf < 55 else []
        return _CellText(text=ocr_text, source_element_ids=[], candidate_element_ids=[item.element_id for item in assigned], confidence=ocr_conf, warnings=warnings, used_cell_ocr=True)
    return _CellText(
        text=text,
        source_element_ids=[item.element_id for item in assigned if text],
        candidate_element_ids=[item.element_id for item in assigned],
        confidence=confidence,
        warnings=warnings,
        used_cell_ocr=False,
    )


def _cell_bbox(cell: Dict[str, Any] | List[int]) -> List[int]:
    if isinstance(cell, dict):
        return list(cell.get("bbox") or [0, 0, 0, 0])
    return list(cell)


def _ocr_cell(image: Image.Image, bbox: List[int]) -> Tuple[str, float]:
    x, y, w, h = bbox
    pad = 3
    crop = image.crop((max(0, x - pad), max(0, y - pad), x + w + pad, y + h + pad))
    try:
        data = pytesseract.image_to_data(
            crop,
            lang=resolve_ocr_lang(),
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        return "", 0.0
    texts: List[str] = []
    confidences: List[float] = []
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        cleaned = str(text or "").strip()
        try:
            confidence = float(conf)
        except Exception:
            confidence = -1
        if not cleaned or confidence < 0:
            continue
        texts.append(cleaned)
        confidences.append(confidence)
    return " ".join(texts).strip(), round(sum(confidences) / max(1, len(confidences)), 2) if confidences else 0.0


def _table_artifact(
    *,
    table_id: str,
    doc_id: str,
    page_id: str,
    page_no: int,
    region_element_id: str,
    structure_element_id: str,
    strategy: str,
    bbox: List[int],
    rows: List[List[str]],
    cell_ids: List[str],
    base_confidence: float,
    cell_confidences: List[float],
    warnings: List[str],
) -> TableArtifact:
    header_index = _header_row_index(rows)
    headers = _headers_for_rows(rows, header_index)
    data_rows: List[Dict[str, Any]] = []
    columns = max([len(row) for row in rows] or [0])
    cell_index = 0
    for row_index, row in enumerate(rows):
        row_cell_ids = cell_ids[cell_index : cell_index + len(row)]
        cell_index += len(row)
        if row_index <= header_index:
            continue
        values: Dict[str, str] = {}
        for col_index in range(columns):
            header = headers[col_index] if col_index < len(headers) else f"col_{col_index + 1}"
            values[header] = row[col_index] if col_index < len(row) else ""
        data_rows.append({"row_index": row_index, "cell_ids": row_cell_ids, "cells": values})
    if not data_rows and rows:
        for row_index, row in enumerate(rows):
            row_cell_ids = cell_ids[row_index * columns : row_index * columns + len(row)]
            values = {f"col_{col_index + 1}": value for col_index, value in enumerate(row)}
            data_rows.append({"row_index": row_index, "cell_ids": row_cell_ids, "cells": values})

    text_confidences = [item for item in cell_confidences if item > 0]
    text_confidence = sum(text_confidences) / max(1, len(text_confidences))
    confidence = round((base_confidence + min(1.0, text_confidence / 100)) / 2, 3)
    final_warnings = sorted(set(warnings))
    status = "pass"
    if any(warning in final_warnings for warning in ["needs_review", "low_cell_ocr_confidence", "low_candidate_confidence"]):
        status = "needs_review"
    elif final_warnings:
        status = "warn"
    if not rows or not cell_ids:
        status = "failed"
        final_warnings = sorted(set(final_warnings + ["table_structure_failed"]))
    return TableArtifact(
        table_id=table_id,
        doc_id=doc_id,
        page_id=page_id,
        page_no=page_no,
        region_element_id=region_element_id,
        structure_element_id=structure_element_id,
        strategy=strategy,
        bbox=bbox,
        row_count=len(rows),
        column_count=columns,
        headers=headers,
        rows=data_rows,
        cell_ids=cell_ids,
        confidence=confidence,
        status=status,
        warnings=final_warnings,
    )


def _table_blocks(
    *,
    doc_id: str,
    page_id: str,
    page_no: int,
    table: TableArtifact,
    structure_id: str,
    cell_ids: List[str],
    next_block_id: Any,
) -> List[BlockArtifact]:
    element_ids = [structure_id] + cell_ids
    warnings = list(table.warnings)
    if table.status == "needs_review":
        warnings = sorted(set(warnings + ["table_needs_review"]))
    markdown = _table_markdown(table)
    payload = json.dumps(table.to_dict(), ensure_ascii=False, sort_keys=True)
    return [
        BlockArtifact(
            block_id=next_block_id(),
            doc_id=doc_id,
            page_id=page_id,
            page_no=page_no,
            text=markdown,
            element_ids=element_ids,
            source_types=["table_cell", "table_markdown", "table_structure"],
            source_group_ids=[table.table_id],
            bbox=table.bbox,
            kind="table",
            role="primary",
            confidence=table.confidence,
            warnings=warnings,
        ),
        BlockArtifact(
            block_id=next_block_id(),
            doc_id=doc_id,
            page_id=page_id,
            page_no=page_no,
            text=payload,
            element_ids=element_ids,
            source_types=["table_cell", "table_json", "table_structure"],
            source_group_ids=[table.table_id],
            bbox=table.bbox,
            kind="table",
            role="primary",
            confidence=table.confidence,
            warnings=warnings,
        ),
    ]


def _table_markdown(table: TableArtifact) -> str:
    headers = table.headers or [f"col_{idx + 1}" for idx in range(table.column_count)]
    lines = [
        f"<!-- table_id: {table.table_id} status: {table.status} strategy: {table.strategy} -->",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in table.rows:
        cells = row.get("cells", {})
        lines.append("| " + " | ".join(str(cells.get(header, "")) for header in headers) + " |")
    return "\n".join(lines)


def _add_line_elements(
    *,
    result: TableParseResult,
    grid: _GridResult,
    doc_id: str,
    page_id: str,
    page_no: int,
    structure_id: str,
    next_element_id: Any,
    add_edge: Any,
) -> List[str]:
    line_ids: List[str] = []
    for idx, bbox in enumerate(grid.line_bboxes, start=1):
        line_id = next_element_id()
        line = ElementArtifact(
            element_id=line_id,
            doc_id=doc_id,
            element_type="table_line",
            source_type="drawing_element",
            page_id=page_id,
            page_no=page_no,
            bbox=bbox,
            parent_element_id=structure_id,
            raw_ref={"line_index": idx},
            extractor={"name": "table_parser.v1.ruling_line"},
            quality={"status": "pass", "signals": []},
        )
        result.elements.append(line)
        line_ids.append(line_id)
        add_edge(structure_id, line_id, "contains", "table_parser.v1.structure_contains_line", {"line_index": idx})
    return line_ids


def _add_axis_elements(
    *,
    result: TableParseResult,
    axis: str,
    bboxes: List[List[int]],
    doc_id: str,
    page_id: str,
    page_no: int,
    structure_id: str,
    next_element_id: Any,
    add_edge: Any,
) -> List[str]:
    ids: List[str] = []
    element_type = "table_row" if axis == "row" else "table_column"
    for idx, bbox in enumerate(bboxes):
        element_id = next_element_id()
        element = ElementArtifact(
            element_id=element_id,
            doc_id=doc_id,
            element_type=element_type,
            source_type=element_type,
            page_id=page_id,
            page_no=page_no,
            bbox=bbox,
            parent_element_id=structure_id,
            raw_ref={f"{axis}_index": idx},
            extractor={"name": "table_parser.v1"},
            quality={"status": "pass", "signals": []},
        )
        result.elements.append(element)
        ids.append(element_id)
        add_edge(structure_id, element_id, "contains", f"table_parser.v1.structure_contains_{axis}", {f"{axis}_index": idx})
    return ids


def _infer_borderless_region(
    doc_id: str,
    page_id: str,
    page_no: int,
    candidates: List[ElementArtifact],
    next_element_id: Any,
) -> Optional[ElementArtifact]:
    layout = _borderless_layout(candidates)
    if layout is None:
        return None
    bboxes = [item.bbox or [0, 0, 0, 0] for row in layout.rows for item in row]
    bbox = _pad_bbox(_union_bbox(bboxes), 8)
    return ElementArtifact(
        element_id=next_element_id(),
        doc_id=doc_id,
        element_type="table_region",
        source_type="table_detection",
        page_id=page_id,
        page_no=page_no,
        bbox=bbox,
        raw_ref={
            "table_id": f"{page_id}-alignment-region",
            "reason": "text_alignment",
            "diagnostics": layout.diagnostics,
        },
        extractor={"name": "table_parser.v1.borderless_region"},
        quality={"status": "info", "signals": ["borderless_table_candidate"]},
    )


def _borderless_layout(candidates: List[ElementArtifact]) -> Optional[_BorderlessLayout]:
    rows = [row for row in _group_elements_by_row(candidates) if len(row) >= 2]
    if len(rows) < 2:
        return None

    tolerance = 28
    min_aligned_rows = max(2, math.ceil(len(rows) * 0.6))
    column_centers = _aligned_column_centers(rows, tolerance=tolerance, min_rows=min_aligned_rows)
    if len(column_centers) < 2:
        return None

    row_hit_counts = [_aligned_hit_count(row, column_centers, tolerance=tolerance) for row in rows]
    min_hits_for_coverage = min(2, len(column_centers))
    covered_rows = sum(1 for count in row_hit_counts if count >= min_hits_for_coverage)
    min_covered_rows = max(2, math.ceil(len(rows) * 0.6))
    if covered_rows < min_covered_rows:
        return None

    complete_threshold = max(2, min(len(column_centers), math.ceil(len(column_centers) * 0.75)))
    complete_rows = sum(1 for count in row_hit_counts if count >= complete_threshold)
    if complete_rows < max(2, math.ceil(len(rows) * 0.5)):
        return None

    row_bboxes = [_union_bbox([item.bbox or [0, 0, 0, 0] for item in row]) for row in rows]
    region_bbox = _union_bbox(row_bboxes)
    region_width = max(1, region_bbox[2])
    first_cells = [row[0].text.strip() for row in rows if row]
    list_like_ratio = sum(1 for text in first_cells if _is_list_marker(text)) / max(1, len(first_cells))
    first_row_starts_list = bool(first_cells and _is_list_marker(first_cells[0]))
    long_row_ratio = sum(1 for row in rows if _is_paragraph_like_row(row, region_width)) / max(1, len(rows))
    split_heading = _is_split_heading_row(rows[0], len(column_centers))
    prose_fragment_ratio = sum(1 for row in rows if _is_fragmented_prose_row(row, region_width)) / max(1, len(rows))

    if first_row_starts_list and list_like_ratio >= 0.35 and (long_row_ratio >= 0.2 or len(column_centers) > 6):
        return None
    if long_row_ratio >= 0.45 and complete_rows < math.ceil(len(rows) * 0.75):
        return None
    if split_heading:
        return None
    if len(column_centers) >= 7 and prose_fragment_ratio >= 0.3 and complete_rows < math.ceil(len(rows) * 0.85):
        return None

    return _BorderlessLayout(
        rows=rows,
        column_centers=column_centers,
        row_bboxes=row_bboxes,
        diagnostics={
            "row_count": len(rows),
            "column_count": len(column_centers),
            "min_aligned_rows": min_aligned_rows,
            "covered_rows": covered_rows,
            "complete_rows": complete_rows,
            "list_like_first_cell_ratio": round(list_like_ratio, 3),
            "long_row_ratio": round(long_row_ratio, 3),
            "split_heading": split_heading,
            "prose_fragment_ratio": round(prose_fragment_ratio, 3),
        },
    )


def _aligned_hit_count(row: List[ElementArtifact], column_centers: List[int], tolerance: float) -> int:
    centers = [_bbox_center(item.bbox or [0, 0, 0, 0])[0] for item in row]
    return sum(1 for center in column_centers if any(abs(item - center) <= tolerance for item in centers))


def _is_list_marker(text: str) -> bool:
    cleaned = text.strip()
    return bool(re.fullmatch(r"([0-9]{1,3}|[A-Za-z]|[a-z])[\.\)、)]", cleaned))


def _is_paragraph_like_row(row: List[ElementArtifact], region_width: int) -> bool:
    for item in row:
        text = item.text.strip()
        bbox = item.bbox or [0, 0, 0, 0]
        if len(text) >= 80 or bbox[2] / max(1, region_width) >= 0.55:
            return True
    return False


def _is_split_heading_row(row: List[ElementArtifact], column_count: int) -> bool:
    texts = [_compact_text(item.text) for item in row if _compact_text(item.text)]
    if column_count < 7 or len(texts) < 4:
        return False
    cjk_single = sum(1 for text in texts if len(text) == 1 and _cjk_char_count(text) == 1)
    cjk_short = sum(1 for text in texts if 1 <= len(text) <= 2 and _cjk_char_count(text) == len(text))
    filled_ratio = len(texts) / max(1, column_count)
    joined = "".join(texts)
    return (
        len(joined) >= 4
        and filled_ratio < 0.8
        and cjk_single / max(1, len(texts)) >= 0.5
        and cjk_short / max(1, len(texts)) >= 0.65
    )


def _is_fragmented_prose_row(row: List[ElementArtifact], region_width: int) -> bool:
    texts = [_compact_text(item.text) for item in row if _compact_text(item.text)]
    if len(texts) < 4:
        return False
    joined = "".join(texts)
    if len(joined) < 24:
        return False
    row_bbox = _union_bbox([item.bbox or [0, 0, 0, 0] for item in row])
    if row_bbox[2] / max(1, region_width) < 0.55:
        return False
    cjk_fragments = sum(1 for text in texts if _cjk_char_count(text) > 0 and len(text) <= 10)
    has_prose_punctuation = bool(re.search(r"[，。；：、,.!?;:]", joined))
    return (
        cjk_fragments / max(1, len(texts)) >= 0.55
        and (_cjk_char_count(joined) >= 24 or has_prose_punctuation)
    )


def _compact_text(text: str) -> str:
    cleaned = re.sub(r"[\u200b-\u200f\ufeff]", "", text.strip())
    return re.sub(r"\s+", "", cleaned)


def _cjk_char_count(text: str) -> int:
    return len(re.findall(r"[\u3400-\u9fff]", text))


def _group_elements_by_row(elements: List[ElementArtifact]) -> List[List[ElementArtifact]]:
    rows: List[List[ElementArtifact]] = []
    for element in sorted([item for item in elements if item.bbox and item.text.strip()], key=lambda item: ((item.bbox or [0, 0, 0, 0])[1], (item.bbox or [0, 0, 0, 0])[0])):
        bbox = element.bbox or [0, 0, 0, 0]
        center_y = bbox[1] + bbox[3] / 2
        if rows:
            row_bbox = _union_bbox([item.bbox or [0, 0, 0, 0] for item in rows[-1]])
            row_center = row_bbox[1] + row_bbox[3] / 2
            if abs(center_y - row_center) <= max(8, max(row_bbox[3], bbox[3]) * 0.7):
                rows[-1].append(element)
                continue
        rows.append([element])
    return [sorted(row, key=lambda item: (item.bbox or [0, 0, 0, 0])[0]) for row in rows]


def _elements_in_bbox(elements: List[ElementArtifact], bbox: List[int], min_overlap: float) -> List[ElementArtifact]:
    result = []
    for element in elements:
        eb = element.bbox or []
        if not _valid_bbox(eb):
            continue
        center = _bbox_center(eb)
        if _point_in_bbox(center, bbox) or _bbox_overlap_candidate_ratio(eb, bbox) >= min_overlap:
            result.append(element)
    return result


def _merge_candidate_text(elements: List[ElementArtifact]) -> str:
    return " ".join(item.text.strip() for item in elements if item.text.strip()).strip()


def _candidate_confidence(elements: List[ElementArtifact]) -> float:
    if not elements:
        return 0.0
    values = []
    for element in elements:
        if element.source_type in {"visible_text", "hidden_text", "form_field"}:
            values.append(100.0)
        elif element.confidence is not None:
            values.append(float(element.confidence if element.confidence > 1 else element.confidence * 100))
        else:
            values.append(50.0)
    return round(sum(values) / max(1, len(values)), 3)


def _has_low_ocr_confidence(elements: List[ElementArtifact]) -> bool:
    ocr = [item for item in elements if "ocr" in str(item.source_type)]
    if not ocr:
        return False
    return _candidate_confidence(ocr) < 55


def _header_row_index(rows: List[List[str]]) -> int:
    for idx, row in enumerate(rows):
        non_empty = [cell for cell in row if cell.strip()]
        if len(non_empty) >= 2:
            return idx
    return 0


def _headers_for_rows(rows: List[List[str]], header_index: int) -> List[str]:
    if not rows:
        return []
    width = max(len(row) for row in rows)
    header_row = rows[header_index] if header_index < len(rows) else []
    headers = []
    seen: Dict[str, int] = {}
    for idx in range(width):
        value = header_row[idx].strip() if idx < len(header_row) else ""
        header = value or f"col_{idx + 1}"
        if header in seen:
            seen[header] += 1
            header = f"{header}_{seen[header]}"
        else:
            seen[header] = 1
        headers.append(header)
    return headers


def _merge_positions(values: List[int], tolerance: int) -> List[int]:
    if not values:
        return []
    groups: List[List[int]] = []
    for value in sorted(values):
        if groups and abs(value - groups[-1][-1]) <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [int(round(sum(group) / len(group))) for group in groups]


def _cluster_positions(values: List[float], tolerance: float) -> List[int]:
    if not values:
        return []
    groups: List[List[float]] = []
    for value in sorted(values):
        if groups and abs(value - (sum(groups[-1]) / len(groups[-1]))) <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [int(round(sum(group) / len(group))) for group in groups]


def _aligned_column_centers(rows: List[List[ElementArtifact]], tolerance: float, min_rows: int) -> List[int]:
    centers_by_row = [[_bbox_center(item.bbox or [0, 0, 0, 0])[0] for item in row] for row in rows]
    all_centers = _cluster_positions([center for row in centers_by_row for center in row], tolerance=tolerance)
    aligned = []
    for center in all_centers:
        row_hits = sum(1 for row in centers_by_row if any(abs(item - center) <= tolerance for item in row))
        if row_hits >= min_rows:
            aligned.append(center)
    return aligned


def _union_bbox(bboxes: List[List[int]]) -> List[int]:
    valid = [bbox for bbox in bboxes if _valid_bbox(bbox)]
    if not valid:
        return [0, 0, 0, 0]
    left = min(bbox[0] for bbox in valid)
    top = min(bbox[1] for bbox in valid)
    right = max(bbox[0] + bbox[2] for bbox in valid)
    bottom = max(bbox[1] + bbox[3] for bbox in valid)
    return [left, top, right - left, bottom - top]


def _pad_bbox(bbox: List[int], pad: int) -> List[int]:
    return [max(0, bbox[0] - pad), max(0, bbox[1] - pad), bbox[2] + pad * 2, bbox[3] + pad * 2]


def _valid_bbox(bbox: List[int]) -> bool:
    return len(bbox) == 4 and bbox[2] > 0 and bbox[3] > 0


def _bbox_center(bbox: List[int]) -> Tuple[float, float]:
    return bbox[0] + bbox[2] / 2, bbox[1] + bbox[3] / 2


def _axis_overlap(a1: float, a2: float, b1: float, b2: float) -> float:
    return max(0.0, min(a2, b2) - max(a1, b1))


def _point_in_bbox(point: Tuple[float, float], bbox: List[int]) -> bool:
    x, y = point
    return bbox[0] <= x <= bbox[0] + bbox[2] and bbox[1] <= y <= bbox[1] + bbox[3]


def _bbox_overlap_ratio(a: List[int], b: List[int]) -> float:
    if not _valid_bbox(a) or not _valid_bbox(b):
        return 0.0
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    return ((ix2 - ix1) * (iy2 - iy1)) / max(1, min(aw * ah, bw * bh))


def _bbox_overlap_candidate_ratio(candidate: List[int], container: List[int]) -> float:
    if not _valid_bbox(candidate) or not _valid_bbox(container):
        return 0.0
    ax1, ay1, aw, ah = candidate
    bx1, by1, bw, bh = container
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    return ((ix2 - ix1) * (iy2 - iy1)) / max(1, aw * ah)
