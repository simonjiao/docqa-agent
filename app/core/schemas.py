from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class PdfProbeResult:
    pdf_type: str
    pages: int
    text_chars: int
    image_blocks: int
    strategy: str
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OCRLine:
    id: str
    page: int
    text: str
    bbox: List[int]  # x, y, w, h in rendered image pixels
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PageRecognition:
    page: int
    image_width: int
    image_height: int
    text: str
    lines: List[OCRLine]
    table_regions: List[Dict[str, Any]]
    average_confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "text": self.text,
            "lines": [line.to_dict() for line in self.lines],
            "table_regions": self.table_regions,
            "average_confidence": self.average_confidence,
        }


@dataclass
class Chunk:
    id: str
    doc_id: str
    page: int
    text: str
    line_ids: List[str]
    kind: str = "text"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
