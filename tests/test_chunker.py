from app.core.chunker import build_chunks
from app.core.schemas import OCRLine, PageRecognition


def test_build_chunks_keeps_page_and_line_ids():
    page = PageRecognition(
        page=1,
        image_width=100,
        image_height=100,
        text="1 范围\n本标准规定...\n3.1 键的抗拉强度...",
        lines=[
            OCRLine(id="p1-l1", page=1, text="1 范围", bbox=[0, 0, 1, 1], confidence=90),
            OCRLine(id="p1-l2", page=1, text="本标准规定...", bbox=[0, 1, 1, 1], confidence=90),
            OCRLine(id="p1-l3", page=1, text="3.1 键的抗拉强度应大于等于 590 MPa。", bbox=[0, 2, 1, 1], confidence=90),
        ],
        table_regions=[],
        average_confidence=90,
    )
    chunks = build_chunks("doc", [page], max_lines=5)
    assert chunks
    assert chunks[0].page == 1
    assert "p1-l1" in chunks[0].line_ids
