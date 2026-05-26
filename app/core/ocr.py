from __future__ import annotations
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple
import os

import fitz
import numpy as np
from PIL import Image
import pytesseract

from .schemas import OCRLine, PageRecognition

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    cv2 = None


DEFAULT_DPI = int(os.getenv("OCR_DPI", "120"))
DEFAULT_LANG = os.getenv("OCR_LANG", "HanS+eng")
DEFAULT_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "30"))


def render_page(pdf_path: Path, page_index: int, out_path: Path, dpi: int = DEFAULT_DPI) -> Tuple[int, int]:
    """Render one PDF page to PNG. page_index is 0-based."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_index)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    pix.save(str(out_path))
    return pix.width, pix.height


def _safe_conf(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return -1.0


def ocr_image(image_path: Path, page_no: int, lang: str = DEFAULT_LANG) -> PageRecognition:
    """OCR rendered page and group words into line records."""
    image = Image.open(image_path)
    try:
        data = pytesseract.image_to_data(
            image,
            lang=lang,
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
            timeout=DEFAULT_TIMEOUT,
        )
    except RuntimeError as exc:
        # Tesseract can hang on noisy scans. Failing fast keeps the pipeline
        # auditable and lets the page enter manual review instead of blocking.
        return PageRecognition(
            page=page_no,
            image_width=image.width,
            image_height=image.height,
            text=f"[OCR_TIMEOUT] {exc}",
            lines=[],
            table_regions=detect_table_regions(image),
            average_confidence=0.0,
        )

    grouped: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
    n = len(data.get("text", []))
    confidences = []
    for i in range(n):
        text = (data["text"][i] or "").strip()
        conf = _safe_conf(str(data["conf"][i]))
        if not text or conf < 0:
            continue
        key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
        grouped[key].append(i)
        confidences.append(conf)

    lines: List[OCRLine] = []
    for line_idx, (_, word_indexes) in enumerate(sorted(grouped.items()), start=1):
        texts = [(data["text"][i] or "").strip() for i in word_indexes]
        line_text = " ".join(t for t in texts if t).strip()
        if not line_text:
            continue
        xs = [int(data["left"][i]) for i in word_indexes]
        ys = [int(data["top"][i]) for i in word_indexes]
        rs = [int(data["left"][i]) + int(data["width"][i]) for i in word_indexes]
        bs = [int(data["top"][i]) + int(data["height"][i]) for i in word_indexes]
        line_conf = sum(_safe_conf(str(data["conf"][i])) for i in word_indexes) / max(1, len(word_indexes))
        lines.append(
            OCRLine(
                id=f"p{page_no}-l{line_idx}",
                page=page_no,
                text=line_text,
                bbox=[min(xs), min(ys), max(rs) - min(xs), max(bs) - min(ys)],
                confidence=round(line_conf, 2),
            )
        )

    text = "\n".join(line.text for line in lines)
    tables = detect_table_regions(image)
    avg_conf = round(sum(confidences) / max(1, len(confidences)), 2)
    return PageRecognition(
        page=page_no,
        image_width=image.width,
        image_height=image.height,
        text=text,
        lines=lines,
        table_regions=tables,
        average_confidence=avg_conf,
    )


def detect_table_regions(image: Image.Image) -> List[dict]:
    """Detect possible table boxes by ruling lines.

    This does not pretend to fully understand a table. It gives the reviewer a
    transparent candidate area so that a later table-specific OCR pass can be
    attached to that region.
    """
    if cv2 is None:
        return []

    arr = np.array(image.convert("L"))
    # Black text/lines become foreground.
    binary = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 35, 15)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (45, 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 35))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    table_mask = cv2.add(horizontal, vertical)
    contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    image_area = image.width * image.height
    for idx, contour in enumerate(contours, start=1):
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < image_area * 0.005 or w < image.width * 0.25 or h < image.height * 0.03:
            continue
        candidates.append({"id": f"table-{idx}", "bbox": [int(x), int(y), int(w), int(h)], "reason": "ruling_lines"})

    candidates.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    return candidates[:5]
