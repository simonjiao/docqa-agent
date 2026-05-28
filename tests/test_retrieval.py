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


def test_retriever_boosts_table_chunks_for_table_questions():
    chunks = [
        Chunk(
            id="body-aql",
            doc_id="d",
            page=3,
            text="键的检查项目和合格质量水平见表 1，样本大小按 GB/T 2828.1 抽取。",
            source_block_ids=["body-block"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["image_ocr"],
        ),
        Chunk(
            id="table-1",
            doc_id="d",
            page=4,
            kind="table",
            text=(
                "| 检查 项 目 | 平 键 | col_3 | col_4 |\n"
                "| --- | --- | --- | --- |\n"
                "| 键 宽 | 1.0 |  |  |\n"
                "| 键 高 | 2.5 |  |  |\n"
            ),
            source_block_ids=["table-block"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["table_cell", "table_markdown", "table_structure"],
        ),
    ]

    result = TfidfRetriever(chunks).search("表1中检查项目有哪些？", top_k=1)

    assert result[0]["chunk_id"] == "table-1"
    assert result[0]["kind"] == "table"


def test_retriever_does_not_treat_surface_as_table_query():
    chunks = [
        Chunk(
            id="marks",
            doc_id="d",
            page=4,
            text="包装箱、盒等外表面应有制造厂名、产品名称、产品数量或净重等标志。",
            source_block_ids=["marks-block"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["image_ocr"],
        ),
        Chunk(
            id="table-1",
            doc_id="d",
            page=4,
            kind="table",
            text=(
                "| 检查 项 目 | 平 键 |\n"
                "| --- | --- |\n"
                "| 键 宽 | 1.0 |\n"
            ),
            source_block_ids=["table-block"],
            alternative_block_ids=[],
            source_group_ids=[],
            source_types=["table_cell", "table_markdown", "table_structure"],
        ),
    ]

    result = TfidfRetriever(chunks).search("包装箱或盒外表面应有哪些标志？", top_k=1)

    assert result[0]["chunk_id"] == "marks"
