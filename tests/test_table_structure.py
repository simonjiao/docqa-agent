from pathlib import Path

from app.core.parser import process_pdf
from app.core.storage import clean_storage, copy_sample, doc_dir, load_document
from app.main import ReviewRequest, get_table, list_doc_tables, list_page_tables, save_review


FIXTURES = Path(__file__).resolve().parents[1] / "docs-for-test"


def _parse_fixture(name: str) -> tuple[str, dict]:
    clean_storage()
    doc_id, pdf_path = copy_sample(FIXTURES / name)
    return doc_id, process_pdf(doc_id, pdf_path)


def _assert_edge_integrity(doc: dict) -> None:
    ids = {item["element_id"] for item in doc["elements"]}
    ids.update(item["block_id"] for item in doc["blocks"])
    ids.update(item["id"] for item in doc["chunks"])
    for edge in doc["edges"]:
        assert edge["from_id"] in ids
        assert edge["to_id"] in ids


def test_ruled_table_writes_structure_artifacts_and_table_chunks():
    doc_id, doc = _parse_fixture("sample_table_ruled.pdf")
    table = doc["tables"][0]

    assert (doc_dir(doc_id) / "tables.jsonl").exists()
    assert doc["manifest"]["outputs"]["tables"] == "tables.jsonl"
    assert table["strategy"] == "ruled_grid"
    assert table["status"] == "pass"
    assert table["headers"] == ["Sample", "Grade", "Code", "Result", "Interpretation"]
    assert table["rows"][0]["cells"]["Sample"] == "CHP01"
    assert table["rows"][0]["cells"]["Code"] == "0"
    assert "46,XN,-5" in table["rows"][0]["cells"]["Result"]
    assert table["rows"][1]["cells"]["Interpretation"] == "Abnormal"
    check_names = {check["name"] for check in doc["pages"][0]["checks"]}
    assert {
        "table_region_coverage",
        "table_grid_confidence",
        "table_text_assignment",
        "table_header_quality",
        "table_ocr_quality",
        "table_chunk_traceability",
    } <= check_names

    table_elements = [item for item in doc["elements"] if item.get("source_group_id") == table["table_id"]]
    assert any(item["element_type"] == "table_structure" for item in table_elements)
    assert sum(1 for item in table_elements if item["element_type"] == "table_cell") == table["row_count"] * table["column_count"]
    assert any(item["element_type"] == "table_line" for item in doc["elements"])

    table_blocks = [block for block in doc["blocks"] if block["kind"] == "table"]
    assert any("table_markdown" in block["source_types"] for block in table_blocks)
    assert any("table_json" in block["source_types"] for block in table_blocks)
    table_chunks = [chunk for chunk in doc["chunks"] if chunk["kind"] == "table"]
    assert table_chunks
    assert all(chunk["source_block_ids"] for chunk in table_chunks)
    table_chunk_edge_sources = {
        edge["from_id"]
        for edge in doc["edges"]
        if edge["edge_type"] == "contributes_to_chunk"
        and edge["to_id"] in {chunk["id"] for chunk in table_chunks}
    }
    assert {block["block_id"] for block in table_blocks} <= table_chunk_edge_sources
    _assert_edge_integrity(doc)

    assert list_doc_tables(doc_id)["items"][0]["table_id"] == table["table_id"]
    assert list_page_tables(doc_id, 1)["items"][0]["table_id"] == table["table_id"]
    assert get_table(doc_id, table["table_id"])["table"]["table_id"] == table["table_id"]

    cell_id = table["cell_ids"][0]
    review = save_review(
        doc_id,
        ReviewRequest(
            question=f"表格单元格复核 {table['table_id']}",
            answer="CHP01",
            result="needs_fix",
            notes="cell review test",
            target_element_ids=[cell_id],
        ),
    )
    assert review["review_edges"]
    updated = load_document(doc_id)
    assert any(
        edge["edge_type"] == "review_of" and edge["to_id"] == cell_id
        for edge in updated["edges"]
    )


def test_borderless_table_uses_alignment_strategy_without_ruling_lines():
    _, doc = _parse_fixture("sample_table_borderless.pdf")
    table = doc["tables"][0]

    assert table["strategy"] == "borderless_alignment"
    assert table["status"] == "pass"
    assert table["headers"] == ["Item", "Qty", "Price", "Owner"]
    assert table["rows"][0]["cells"] == {
        "Item": "Alpha",
        "Qty": "12",
        "Price": "35.50",
        "Owner": "Ops",
    }
    assert any(
        item["element_type"] == "table_region"
        and item.get("raw_ref", {}).get("reason") == "text_alignment"
        for item in doc["elements"]
    )
    _assert_edge_integrity(doc)


def test_scanned_low_confidence_table_keeps_cells_and_requires_review():
    _, doc = _parse_fixture("sample_table_scanned_low_conf.pdf")
    table = doc["tables"][0]

    assert table["strategy"] == "scanned_ocr_table"
    assert table["status"] == "needs_review"
    assert table["row_count"] >= 2
    assert table["column_count"] >= 2
    assert table["cell_ids"]
    assert "scanned_table_needs_review" in table["warnings"]
    assert any(item["source_type"] == "cell_ocr" for item in doc["elements"])

    table_chunks = [chunk for chunk in doc["chunks"] if chunk["kind"] == "table"]
    assert table_chunks
    assert any("table_needs_review" in chunk["warnings"] for chunk in table_chunks)
    _assert_edge_integrity(doc)
