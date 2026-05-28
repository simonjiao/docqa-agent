from pathlib import Path

from app.core.parser import process_pdf
from app.core.storage import append_review, clean_storage, copy_sample, doc_dir, load_document


def test_process_pdf_writes_element_graph_artifacts():
    clean_storage()
    sample = Path(__file__).resolve().parents[1] / "docs-for-test" / "sample_scan.pdf"
    doc_id, pdf_path = copy_sample(sample)

    result = process_pdf(doc_id, pdf_path)
    root = doc_dir(doc_id)

    assert "manifest" in result
    for name in ["manifest.json", "pages.jsonl", "elements.jsonl", "edges.jsonl", "blocks.jsonl", "chunks.jsonl", "derived/full.md"]:
        assert (root / name).exists()

    assert not (root / "meta.json").exists()
    assert not (root / "pages.json").exists()
    assert not (root / "chunks.json").exists()

    doc = load_document(doc_id)
    assert doc["pages"]
    assert doc["elements"]
    assert doc["edges"]
    assert doc["blocks"]
    assert doc["chunks"]

    ids = {item["element_id"] for item in doc["elements"]}
    ids.update(item["block_id"] for item in doc["blocks"])
    ids.update(item["id"] for item in doc["chunks"])
    for edge in doc["edges"]:
        assert edge["from_id"] in ids
        assert edge["to_id"] in ids

    ocr_ids = {item["element_id"] for item in doc["elements"] if item["element_type"] == "ocr_text"}
    ocr_edge_targets = {edge["to_id"] for edge in doc["edges"] if edge["edge_type"] == "ocr_derived_from"}
    assert ocr_ids
    assert ocr_ids <= ocr_edge_targets

    chunk_ids = {item["id"] for item in doc["chunks"]}
    chunk_edge_targets = {edge["to_id"] for edge in doc["edges"] if edge["edge_type"] == "contributes_to_chunk"}
    assert chunk_ids <= chunk_edge_targets


def test_ocr_pdf_keeps_image_text_and_alternative_chunk_links():
    clean_storage()
    sample = Path(__file__).resolve().parents[1] / "docs-for-test" / "sample_ocr.pdf"
    doc_id, pdf_path = copy_sample(sample)

    doc = process_pdf(doc_id, pdf_path)

    primary_blocks = [block for block in doc["blocks"] if block["role"] == "primary"]
    alternative_blocks = [block for block in doc["blocks"] if block["role"] == "alternative"]
    assert any("image_ocr" in block["source_types"] for block in primary_blocks)
    assert alternative_blocks

    alternative_edges = [edge for edge in doc["edges"] if edge["edge_type"] == "alternative_for_chunk"]
    assert alternative_edges
    alternative_block_ids = {block["block_id"] for block in alternative_blocks}
    assert {edge["from_id"] for edge in alternative_edges} <= alternative_block_ids
    assert any(chunk["alternative_block_ids"] for chunk in doc["chunks"])


def test_review_writes_review_of_edges():
    clean_storage()
    sample = Path(__file__).resolve().parents[1] / "docs-for-test" / "sample_scan.pdf"
    doc_id, pdf_path = copy_sample(sample)
    doc = process_pdf(doc_id, pdf_path)
    target_chunk_id = doc["chunks"][0]["id"]
    target_block_id = doc["chunks"][0]["source_block_ids"][0]

    result = append_review(
        doc_id,
        {
            "review_id": "review-test-1",
            "question": "测试问题",
            "answer": "测试答案",
            "result": "accepted",
            "notes": "人工复核通过",
            "evidence": [],
            "target_chunk_ids": [target_chunk_id],
            "target_block_ids": [target_block_id],
        },
    )

    assert result["edges"]
    updated = load_document(doc_id)
    ids = {item["element_id"] for item in updated["elements"]}
    ids.update(item["block_id"] for item in updated["blocks"])
    ids.update(item["id"] for item in updated["chunks"])

    review_elements = [item for item in updated["elements"] if item["element_type"] == "review"]
    assert {item["element_id"] for item in review_elements} == {"review-test-1"}

    review_edges = [edge for edge in updated["edges"] if edge["edge_type"] == "review_of"]
    assert {edge["to_id"] for edge in review_edges} == {target_chunk_id, target_block_id}
    for edge in review_edges:
        assert edge["from_id"] in ids
        assert edge["to_id"] in ids
