from pathlib import Path
from app.core.pdf_probe import probe_pdf

FIXTURES = Path(__file__).resolve().parents[1] / "docs-for-test"


def test_probe_sample_pdf_scanned_or_hybrid():
    sample = FIXTURES / "sample_scan.pdf"
    result = probe_pdf(sample)
    assert result.pages == 4
    assert result.pdf_type in {"scan_pdf", "mixed_pdf", "text_pdf", "ocr_pdf", "drawing_pdf"}
    assert result.strategy
    assert result.pdf_type_candidates


def test_probe_fixture_pdf_types():
    cases = {
        "sample_text.pdf": "text_pdf",
        "sample_scan.pdf": "scan_pdf",
        "sample_ocr.pdf": "ocr_pdf",
        "sample_form.pdf": "form_pdf",
        "sample_protected.pdf": "protected_pdf",
        "sample_drawing.pdf": "drawing_pdf",
    }
    for filename, expected_type in cases.items():
        result = probe_pdf(FIXTURES / filename)
        assert result.pdf_type == expected_type
