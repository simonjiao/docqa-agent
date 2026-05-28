from app.main import _page_recognition_lines


def test_page_recognition_prefers_primary_blocks_over_raw_ocr_lines():
    doc = {
        "blocks": [
            {
                "block_id": "p0001-b0001",
                "page_no": 1,
                "role": "primary",
                "text": "多智能体平台JD",
                "bbox": [10, 20, 300, 40],
                "confidence": 1.0,
                "source_types": ["visible_text"],
                "source_group_ids": [],
            }
        ],
        "elements": [
            {
                "element_id": "p0001-e0009",
                "page_no": 1,
                "element_type": "ocr_text",
                "source_type": "image_ocr",
                "text": "SSAA AID",
                "bbox": [10, 20, 300, 40],
                "confidence": 17,
                "raw_ref": {"ocr_line_id": "p1-l1"},
            }
        ],
    }

    lines = _page_recognition_lines(doc, 1)

    assert lines[0]["id"] == "p0001-b0001"
    assert lines[0]["text"] == "多智能体平台JD"
    assert lines[0]["source_type"] == "visible_text"
