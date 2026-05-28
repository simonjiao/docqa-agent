from pathlib import Path

from app.core.parser import process_pdf
from app.core.storage import clean_storage, copy_sample, doc_dir, load_document


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
