from __future__ import annotations
import re
from typing import List
from .schemas import Chunk, PageRecognition

SECTION_RE = re.compile(r"^\s*((\d+(?:\.\d+)*|[一二三四五六七八九十]+)[、.．\s]+)")


def build_chunks(doc_id: str, pages: List[PageRecognition], max_lines: int = 5) -> List[Chunk]:
    """Build small, source-traceable chunks from OCR lines.

    The chunker prefers section boundaries but keeps max_lines small so answers
    can cite compact evidence. This is intentionally simple and inspectable.
    """
    chunks: List[Chunk] = []
    for page in pages:
        current_lines = []
        current_ids = []
        for line in page.lines:
            is_heading = bool(SECTION_RE.match(line.text))
            if current_lines and (is_heading or len(current_lines) >= max_lines):
                chunks.append(_make_chunk(doc_id, page.page, len(chunks) + 1, current_lines, current_ids))
                current_lines, current_ids = [], []
            current_lines.append(line.text)
            current_ids.append(line.id)
        if current_lines:
            chunks.append(_make_chunk(doc_id, page.page, len(chunks) + 1, current_lines, current_ids))
    return chunks


def _make_chunk(doc_id: str, page: int, seq: int, lines: List[str], line_ids: List[str]) -> Chunk:
    text = "\n".join(lines).strip()
    kind = "table" if "表" in text or "AQL" in text or "检查项目" in text else "text"
    return Chunk(id=f"c{seq:04d}", doc_id=doc_id, page=page, text=text, line_ids=line_ids, kind=kind)
