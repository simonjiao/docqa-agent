from app.core.parser import _build_blocks_from_elements
from app.core.schemas import ElementArtifact


def test_build_blocks_merges_single_character_text_spans_on_same_line():
    elements = [
        ElementArtifact(
            element_id=f"p0001-e{idx:04d}",
            doc_id="doc",
            element_type="text_span",
            source_type="visible_text",
            page_id="p0001",
            page_no=1,
            text=text,
            bbox=[x, 20, 18, 24],
            reading_order=idx,
        )
        for idx, (text, x) in enumerate([("多", 10), ("智", 29), ("能", 48), ("体", 67), ("平", 86), ("台", 105)], start=1)
    ]

    blocks = _build_blocks_from_elements("doc", "p0001", 1, elements, start_index=1)

    assert len(blocks) == 1
    assert blocks[0].text == "多智能体平台"
    assert blocks[0].element_ids == [element.element_id for element in elements]
