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


def test_retriever_expands_national_standard_aliases():
    chunks = [
        Chunk(
            id="cover",
            doc_id="d",
            page=1,
            text="中华人民共和国国家标准\nGB/T 1568—2008\n键 技术条件",
            source_block_ids=["cover-block"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["image_ocr"],
        ),
        Chunk(
            id="body",
            doc_id="d",
            page=3,
            text="键的抗拉强度应大于等于 590 MPa。",
            source_block_ids=["body-block"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["image_ocr"],
        ),
    ]

    result = TfidfRetriever(chunks).search("这是什么国标", top_k=1)

    assert result[0]["chunk_id"] == "cover"
