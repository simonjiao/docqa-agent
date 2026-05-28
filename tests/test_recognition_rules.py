from PIL import Image

from app.core.recognition_rules import apply_document_recognition_rules, is_excluded_from_primary_text, is_ignored_by_recognition_rule
from app.core.schemas import ElementArtifact


def _ocr_element(seq: int, text: str, bbox: list[int]) -> ElementArtifact:
    return ElementArtifact(
        element_id=f"p0001-e{seq:04d}",
        doc_id="doc",
        element_type="ocr_text",
        source_type="image_ocr",
        page_id="p0001",
        page_no=1,
        text=text,
        bbox=bbox,
        reading_order=seq,
        confidence=80,
        source_group_id=f"p0001-g{seq:04d}",
    )


def test_external_chinese_standard_rules_repair_cover_ocr(monkeypatch, tmp_path):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (945, 1370), "white").save(image_path)
    monkeypatch.setattr(
        "app.core.recognition_rules._ocr_region",
        lambda image_path, bbox, rule: "ICS 21. 120. 30\nJ 18",
    )
    ocr_elements = [
        _ocr_element(5, '40°" 120. 30 a', [85, 28, 736, 32]),
        _ocr_element(6, "( = =", [647, 51, 176, 69]),
        _ocr_element(7, "中 华人 民 共 和 国 国 家 标准", [87, 170, 806, 63]),
        _ocr_element(8, "GB/T 1568 一 2008", [683, 255, 185, 32]),
        _ocr_element(9, "代 赴 GB/T 1568 一 1997", [689, 274, 179, 31]),
        _ocr_element(10, "键 ”技术 条 件", [354, 520, 271, 61]),
    ]

    result = apply_document_recognition_rules(
        doc_id="GBT1568-2008键技术条件-e724ad081078fa41",
        source_filename="source.pdf",
        page_no=1,
        image_path=image_path,
        image_width=945,
        image_height=1370,
        page_elements=[],
        ocr_elements=ocr_elements,
    )

    assert result.profile_ids == ["chinese_national_standard"]
    assert ocr_elements[0].text == "ICS 21.120.30\nJ 18"
    assert is_ignored_by_recognition_rule(ocr_elements[1])
    assert ocr_elements[2].text == "中华人民共和国国家标准"
    assert ocr_elements[3].text == "GB/T 1568—2008"
    assert ocr_elements[4].text == "代替 GB/T 1568—1997"
    assert ocr_elements[5].text == "键 技术条件"
    assert "original_text" in ocr_elements[0].raw_ref


def test_footer_latin_and_roman_page_numbers_are_metadata(monkeypatch, tmp_path):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (945, 1370), "white").save(image_path)
    monkeypatch.setattr("app.core.recognition_rules._ocr_region", lambda image_path, bbox, rule: "")
    ocr_elements = [
        _ocr_element(1, "GB/T 1568—2008", [70, 40, 150, 20]),
        _ocr_element(2, "本 标准 规定 了 H2SO4 + NaOH -> Na2SO4 的 示例 数据。", [90, 300, 620, 30]),
        _ocr_element(3, "IV", [860, 1267, 12, 11]),
        _ocr_element(4, "23", [80, 1267, 12, 11]),
    ]

    apply_document_recognition_rules(
        doc_id="GBT1568-2008键技术条件-e724ad081078fa41",
        source_filename="source.pdf",
        page_no=2,
        image_path=image_path,
        image_width=945,
        image_height=1370,
        page_elements=[],
        ocr_elements=ocr_elements,
    )

    assert "page_number" not in ocr_elements[1].quality["signals"]
    assert "H2SO4 + NaOH -> Na2SO4" in ocr_elements[1].text
    assert ocr_elements[2].raw_ref["semantic_type"] == "page_number"
    assert ocr_elements[3].raw_ref["semantic_type"] == "page_number"


def test_gb_running_title_rewrite_is_region_scoped(monkeypatch, tmp_path):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (945, 1370), "white").save(image_path)
    monkeypatch.setattr("app.core.recognition_rules._ocr_region", lambda image_path, bbox, rule: "")
    standard_code = _ocr_element(0, "GB/T 1568—2008", [700, 100, 140, 24])
    context = _ocr_element(1, "本标准规定了技术要求。", [100, 300, 260, 24])
    title = _ocr_element(2, "键 RARE", [394, 193, 155, 24])
    body = _ocr_element(3, "键 RARE 是一个示例变量。", [100, 600, 260, 24])
    for element in [standard_code, context, title, body]:
        element.page_id = "p0003"
        element.page_no = 3

    apply_document_recognition_rules(
        doc_id="GBT1568-2008键技术条件-e724ad081078fa41",
        source_filename="source.pdf",
        page_no=3,
        image_path=image_path,
        image_width=945,
        image_height=1370,
        page_elements=[],
        ocr_elements=[standard_code, context, title, body],
    )

    assert title.text == "键 技术条件"
    assert body.text == "键 RARE 是一个示例变量。"


def test_body_standard_number_header_is_metadata(monkeypatch, tmp_path):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (945, 1370), "white").save(image_path)
    monkeypatch.setattr("app.core.recognition_rules._ocr_region", lambda image_path, bbox, rule: "")
    header_right = _ocr_element(1, "GB/T 1568—2008", [718, 101, 138, 31])
    header_left = _ocr_element(2, "GB/T 1568—2008", [87, 105, 137, 15])
    body_reference = _ocr_element(3, "本标准是对 GB/T 1568—1997 的修订。", [140, 254, 402, 29])
    for element in [header_right, header_left, body_reference]:
        element.page_id = "p0003"
        element.page_no = 3

    apply_document_recognition_rules(
        doc_id="GBT1568-2008键技术条件-e724ad081078fa41",
        source_filename="source.pdf",
        page_no=3,
        image_path=image_path,
        image_width=945,
        image_height=1370,
        page_elements=[],
        ocr_elements=[header_right, header_left, body_reference],
    )

    assert header_right.raw_ref["semantic_type"] == "standard_number_header"
    assert header_left.raw_ref["semantic_type"] == "standard_number_header"
    assert is_excluded_from_primary_text(header_right)
    assert is_excluded_from_primary_text(header_left)
    assert not is_excluded_from_primary_text(body_reference)
