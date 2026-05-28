from app.core.ocr import resolve_ocr_lang


def test_resolve_ocr_lang_maps_hans_to_available_chinese_language(monkeypatch):
    monkeypatch.delenv("OCR_LANG", raising=False)
    available = ["eng", "chi_sim", "script/HanS"]

    assert resolve_ocr_lang("HanS+eng", available=available) == "chi_sim+eng"
    assert resolve_ocr_lang(None, available=available) == "chi_sim+eng"


def test_resolve_ocr_lang_can_fallback_to_script_hans():
    available = ["eng", "script/HanS"]

    assert resolve_ocr_lang("HanS+eng", available=available) == "script/HanS+eng"
