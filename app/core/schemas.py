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
    pdf_type_candidates: List[str]
    has_text_layer: bool
    has_hidden_text: bool
    has_images: bool
    has_forms: bool
    has_vector_drawings: bool
    is_encrypted: bool
    permission: Dict[str, Any]

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
class PageArtifact:
    page_id: str
    page_no: int
    width: int
    height: int
    image_path: str
    page_type: str
    strategy: str
    text_layer_chars: int
    ocr_chars: int
    image_blocks: int
    table_region_count: int
    average_ocr_confidence: float
    warnings: List[str]
    checks: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ElementArtifact:
    element_id: str
    doc_id: str
    element_type: str
    source_type: str
    page_id: Optional[str] = None
    page_no: Optional[int] = None
    text: str = ""
    bbox: Optional[List[int]] = None
    bbox_unit: str = "px"
    coordinate_space: str = "page_image"
    z_order: int = 0
    reading_order: int = 0
    confidence: Optional[float] = None
    parent_element_id: Optional[str] = None
    source_group_id: Optional[str] = None
    raw_ref: Dict[str, Any] = None  # type: ignore[assignment]
    extractor: Dict[str, Any] = None  # type: ignore[assignment]
    quality: Dict[str, Any] = None  # type: ignore[assignment]
    links: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.raw_ref = self.raw_ref or {}
        self.extractor = self.extractor or {}
        self.quality = self.quality or {"status": "info", "signals": []}
        self.links = self.links or {}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EdgeArtifact:
    edge_id: str
    from_id: str
    to_id: str
    edge_type: str
    rule_id: str
    evidence: Dict[str, Any]
    created_by: str = "parser"
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlockArtifact:
    block_id: str
    doc_id: str
    page_id: str
    page_no: int
    text: str
    element_ids: List[str]
    source_types: List[str]
    bbox: List[int]
    kind: str = "text"
    role: str = "primary"
    source_group_ids: List[str] = None  # type: ignore[assignment]
    confidence: float = 0.0
    warnings: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.source_group_ids = self.source_group_ids or []
        self.warnings = self.warnings or []

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Chunk:
    id: str
    doc_id: str
    page: int
    text: str
    source_block_ids: List[str]
    alternative_block_ids: List[str]
    source_group_ids: List[str]
    source_types: List[str]
    kind: str = "text"
    confidence: float = 0.0
    warnings: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.warnings = self.warnings or []

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
