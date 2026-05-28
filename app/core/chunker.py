from __future__ import annotations
import re
from typing import List, Tuple
from .schemas import BlockArtifact, Chunk, EdgeArtifact

SECTION_RE = re.compile(r"^\s*((\d+(?:\.\d+)*|[一二三四五六七八九十]+)[、.．\s]+)")


def build_chunks(doc_id: str, blocks: List[BlockArtifact], max_blocks: int = 5) -> Tuple[List[Chunk], List[EdgeArtifact]]:
    """Build source-traceable chunks from block artifacts."""
    chunks: List[Chunk] = []
    edges: List[EdgeArtifact] = []
    current: List[BlockArtifact] = []

    def flush() -> None:
        if not current:
            return
        chunk = _make_chunk(doc_id, len(chunks) + 1, current)
        chunks.append(chunk)
        for block in current:
            edges.append(
                EdgeArtifact(
                    edge_id=f"edge-chunk-{len(edges) + 1:06d}",
                    from_id=block.block_id,
                    to_id=chunk.id,
                    edge_type="contributes_to_chunk",
                    rule_id="chunker.v1.block_window",
                    evidence={"page_no": block.page_no, "block_id": block.block_id},
                    confidence=1.0,
                )
            )
        for alt_block_id in chunk.alternative_block_ids:
            edges.append(
                EdgeArtifact(
                    edge_id=f"edge-chunk-{len(edges) + 1:06d}",
                    from_id=alt_block_id,
                    to_id=chunk.id,
                    edge_type="alternative_for_chunk",
                    rule_id="chunker.v1.alternative_block",
                    evidence={"chunk_id": chunk.id, "alternative_block_id": alt_block_id},
                    confidence=1.0,
                )
            )
        current.clear()

    for block in blocks:
        is_heading = bool(SECTION_RE.match(block.text))
        if current and (is_heading or len(current) >= max_blocks or current[-1].page_no != block.page_no):
            flush()
        current.append(block)
    flush()
    return chunks, edges


def _make_chunk(doc_id: str, seq: int, blocks: List[BlockArtifact]) -> Chunk:
    text = "\n".join(block.text for block in blocks).strip()
    kind = "table" if "表" in text or "AQL" in text or "检查项目" in text else "text"
    source_types = sorted({source_type for block in blocks for source_type in block.source_types})
    source_group_ids = sorted({group_id for block in blocks for group_id in block.source_group_ids})
    confidence = round(sum(block.confidence for block in blocks) / max(1, len(blocks)), 3)
    warnings = sorted({warning for block in blocks for warning in block.warnings})
    return Chunk(
        id=f"c{seq:04d}",
        doc_id=doc_id,
        page=blocks[0].page_no,
        text=text,
        source_block_ids=[block.block_id for block in blocks],
        alternative_block_ids=[],
        source_group_ids=source_group_ids,
        source_types=source_types,
        kind=kind,
        confidence=confidence,
        warnings=warnings,
    )
