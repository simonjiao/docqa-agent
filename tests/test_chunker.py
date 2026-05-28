from app.core.chunker import build_chunks
from app.core.schemas import BlockArtifact


def test_build_chunks_keeps_block_trace_edges():
    blocks = [
        BlockArtifact(
            block_id="p0001-b0001",
            doc_id="doc",
            page_id="p0001",
            page_no=1,
            text="1 范围",
            element_ids=["p0001-e0001"],
            source_types=["image_ocr"],
            source_group_ids=["p0001-g0001"],
            bbox=[0, 0, 1, 1],
            confidence=90,
        ),
        BlockArtifact(
            block_id="p0001-b0002",
            doc_id="doc",
            page_id="p0001",
            page_no=1,
            text="3.1 键的抗拉强度应大于等于 590 MPa。",
            element_ids=["p0001-e0002"],
            source_types=["image_ocr"],
            source_group_ids=["p0001-g0002"],
            bbox=[0, 2, 1, 1],
            confidence=90,
        ),
    ]
    chunks, edges = build_chunks("doc", blocks, max_blocks=5)
    assert chunks
    assert chunks[0].page == 1
    assert "p0001-b0001" in chunks[0].source_block_ids
    assert any(edge.edge_type == "contributes_to_chunk" for edge in edges)
