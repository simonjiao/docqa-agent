from pathlib import Path

from app.core.parser import _usable_ocr_elements, process_pdf
from app.core.schemas import ElementArtifact
from app.core.storage import clean_storage, copy_sample, doc_dir, load_document
from app.core.table_parser import _borderless_layout
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


def test_ruled_table_merged_row_uses_col_span_without_copying_value():
    _, doc = _parse_fixture("sample_table_merged_row.pdf")
    table = doc["tables"][0]

    assert table["strategy"] == "ruled_grid"
    assert table["status"] == "pass"
    cells = [
        item
        for item in doc["elements"]
        if item["element_type"] == "table_cell"
        and item.get("source_group_id") == table["table_id"]
    ]
    single_cell_values = [cell for cell in cells if cell.get("text") == "Single Cell"]
    assert len(single_cell_values) == 1
    assert single_cell_values[0]["raw_ref"]["column_index"] == 1
    assert single_cell_values[0]["raw_ref"]["col_span"] == 3
    assert table["rows"][0]["cells"]["col_2"] == "Single Cell"
    assert "Single Cell" not in table["rows"][0]["cells"]["Report Date"]
    assert "Single Cell" not in table["rows"][0]["cells"]["2025-12-29"]


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


def test_split_heading_paragraphs_are_not_inferred_as_borderless_table():
    elements = []
    x_positions = [40, 120, 220, 320, 420, 520, 620, 740, 860]
    rows = [
        ["多", "智", "能 体", "平", "台", "JD"],
        ["1.", "", "", "", "", "", "Senior Multi-Agent Platform Engineer", "", ""],
        ["我 们", "在 做", "什么", "", "", "", "", "", ""],
        ["我 们 正", "在 建", "设 一个", "面 向 复", "杂 知 识", "工 作", "和 长 期 自", "主 任 务 的 新 一", "代 多 智 能 体 AI 平 台 。"],
        ["系 统 已", "经 完", "成 早 期", "原 型 验", "证 ，", "下一 阶", "段 将 进 入", "平 台 化 、 工 程", "化 和 长 期 运 行 阶 段 。"],
        ["体 协 同", "、 复", "杂", "Agent workflow", "", "、 长 期", "任 务 执 行", "、 结 构 化 状", "态 、 工 具 调 用 、 记 忆 系 统 。"],
    ]
    for row_index in range(18):
        row = rows[row_index] if row_index < len(rows) else [
            "原 型 系",
            "统 的",
            "架构 级",
            "重 构 ，",
            "设计 统",
            "一 的",
            "Agent 抽",
            "象 、 任 务 调 度",
            "、 状 态 记 忆 和 工 具 治 理 。",
        ]
        y = 120 + row_index * 34
        for col_index, text in enumerate(row):
            if not text:
                continue
            elements.append(
                ElementArtifact(
                    element_id=f"p0001-e{row_index:04d}-{col_index}",
                    doc_id="doc",
                    element_type="visible_text",
                    source_type="visible_text",
                    page_id="p0001",
                    page_no=1,
                    text=text,
                    bbox=[x_positions[col_index], y, max(24, len(text) * 12), 18],
                )
            )

    assert _borderless_layout(elements) is None


def test_numbered_notes_are_not_inferred_as_borderless_table():
    _, doc = _parse_fixture("sample_text_numbered_notes.pdf")

    assert doc["tables"] == []
    assert not any(block["kind"] == "table" for block in doc["blocks"])
    assert not any(
        item["element_type"] == "table_region"
        and item.get("raw_ref", {}).get("reason") == "text_alignment"
        for item in doc["elements"]
    )
    _assert_edge_integrity(doc)


def test_chart_image_rulings_are_not_promoted_to_table():
    _, doc = _parse_fixture("sample_chart_image_not_table.pdf")

    assert doc["tables"] == []
    assert any(item["element_type"] == "image_object" for item in doc["elements"])
    assert not any(item["element_type"] == "table_region" for item in doc["elements"])
    assert not any(block["kind"] == "table" for block in doc["blocks"])
    table_checks = [
        check
        for page in doc["pages"]
        for check in page["checks"]
        if check["name"] == "table_region_detection"
    ]
    assert table_checks
    assert "已抑制" in table_checks[0]["detail"]
    _assert_edge_integrity(doc)


def test_thin_chart_axis_ocr_labels_are_not_primary_text_candidates():
    image = ElementArtifact(
        element_id="p0001-e0001",
        doc_id="doc",
        element_type="image_object",
        source_type="image",
        page_id="p0001",
        page_no=1,
        bbox=[60, 680, 850, 110],
    )
    chart_tick = ElementArtifact(
        element_id="p0001-e0002",
        doc_id="doc",
        element_type="ocr_text",
        source_type="image_ocr",
        page_id="p0001",
        page_no=1,
        text="3",
        bbox=[62, 690, 16, 11],
        confidence=65,
    )
    scan_text = ElementArtifact(
        element_id="p0001-e0003",
        doc_id="doc",
        element_type="ocr_text",
        source_type="image_ocr",
        page_id="p0001",
        page_no=1,
        text="3",
        bbox=[62, 690, 16, 11],
        confidence=65,
    )
    full_page_image = ElementArtifact(
        element_id="p0001-e0004",
        doc_id="doc",
        element_type="image_object",
        source_type="image",
        page_id="p0001",
        page_no=1,
        bbox=[0, 0, 900, 1200],
    )

    assert _usable_ocr_elements([chart_tick], [image]) == []
    assert _usable_ocr_elements([scan_text], [full_page_image]) == [scan_text]


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
