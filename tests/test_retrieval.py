from app.core.retrieval import TfidfRetriever
from app.core.schemas import Chunk


def test_tfidf_retriever_returns_relevant_chunk():
    chunks = [
        Chunk(id="c1", doc_id="d", page=1, text="键的抗拉强度应大于等于 590 MPa。", line_ids=[]),
        Chunk(id="c2", doc_id="d", page=2, text="包装箱外表面应有制造厂名和产品名称。", line_ids=[]),
    ]
    result = TfidfRetriever(chunks).search("抗拉强度是多少？", top_k=1)
    assert result[0]["chunk_id"] == "c1"
