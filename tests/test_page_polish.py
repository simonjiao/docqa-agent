from app.core.page_polish import page_text_from_lines, polish_page_text


class FakeLLM:
    model = "fake-polish-model"

    def __init__(self, answer: str):
        self.answer = answer
        self.system_prompt = ""
        self.user_prompt = ""

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.answer


def test_page_text_from_lines_keeps_line_ids():
    text = page_text_from_lines([
        {"id": "p0001-b0001", "text": "  标题  "},
        {"id": "p0001-b0002", "text": "第一条  内容"},
        {"id": "empty", "text": "   "},
    ])

    assert "[p0001-b0001] 标题" in text
    assert "[p0001-b0002] 第一条 内容" in text
    assert "empty" not in text


def test_polish_page_text_uses_llm_for_typos_paragraphs_and_lists():
    llm = FakeLLM("## 疑似错别字/OCR错误\n- 技未 -> 技术\n\n## 整理后的段落和列表\n1. 键 技术条件")
    result = polish_page_text(
        page_no=3,
        lines=[
            {"id": "p0003-b0001", "text": "键 技未条件"},
            {"id": "p0003-b0002", "text": "1 范围"},
        ],
        llm_client=llm,
    )

    assert result["model"] == "fake-polish-model"
    assert "技未 -> 技术" in result["output"]
    assert result["source_line_ids"] == ["p0003-b0001", "p0003-b0002"]
    assert "错别字" in llm.system_prompt
    assert "段落和列表" in llm.system_prompt
    assert "[p0003-b0001] 键 技未条件" in llm.user_prompt


def test_polish_page_text_returns_message_for_empty_page_without_llm():
    llm = FakeLLM("should not be used")

    result = polish_page_text(page_no=1, lines=[], llm_client=llm)

    assert result["output"] == "当前页没有可整理的识别文本。"
    assert llm.user_prompt == ""
