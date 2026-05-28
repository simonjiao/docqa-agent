from app.core.retrieval import TfidfRetriever
from app.core.schemas import Chunk


def test_tfidf_retriever_returns_relevant_chunk():
    chunks = [
        Chunk(
            id="c1",
            doc_id="d",
            page=1,
            text="键的抗拉强度应大于等于 590 MPa。",
            source_block_ids=["b1"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["image_ocr"],
        ),
        Chunk(
            id="c2",
            doc_id="d",
            page=2,
            text="包装箱外表面应有制造厂名和产品名称。",
            source_block_ids=["b2"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["image_ocr"],
        ),
    ]
    result = TfidfRetriever(chunks).search("抗拉强度是多少？", top_k=1)
    assert result[0]["chunk_id"] == "c1"
    assert result[0]["source_block_ids"] == ["b1"]
