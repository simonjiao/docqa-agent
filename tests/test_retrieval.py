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


def test_retriever_prioritizes_current_standard_release_date():
    chunks = [
        Chunk(
            id="release",
            doc_id="d",
            page=1,
            text="Technical specifications for keys\n2008-09-22 发布 2009-05-01 实施\n中华人民共和国国家质量监督检验检疫总局发布",
            source_block_ids=["release-block"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["image_ocr"],
        ),
        Chunk(
            id="product-date",
            doc_id="d",
            page=4,
            text="e) 制造或出厂日期。",
            source_block_ids=["product-block"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["image_ocr"],
        ),
        Chunk(
            id="storage",
            doc_id="d",
            page=4,
            text="在正常的运输和保管条件下，应保证自出厂之日起一年内不生锈。",
            source_block_ids=["storage-block"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["image_ocr"],
        ),
    ]
    retriever = TfidfRetriever(chunks)

    assert retriever.search("哪一年发布的", top_k=1)[0]["chunk_id"] == "release"
    assert retriever.search("发布日期", top_k=1)[0]["chunk_id"] == "release"
