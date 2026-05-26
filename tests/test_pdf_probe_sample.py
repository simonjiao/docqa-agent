from pathlib import Path
from app.core.pdf_probe import probe_pdf


def test_probe_sample_pdf_scanned_or_hybrid():
    sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "GBT 1568-2008 键 技术条件.pdf"
    result = probe_pdf(sample)
    assert result.pages == 4
    assert result.pdf_type in {"scanned_pdf", "hybrid_or_unknown_pdf", "text_layer_pdf"}
    assert result.strategy
