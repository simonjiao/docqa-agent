import pytest

from app.core.qa import LLMConfigurationError, build_answer
from app.core.validators import answer_self_checks, recognition_checks


class FakeLLM:
    model = "fake-test-model"

    def __init__(self, answer: str):
        self.answer = answer
        self.user_prompt = ""

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.user_prompt = user_prompt
        return self.answer


def test_build_answer_requires_llm_configuration(monkeypatch):
    monkeypatch.setenv("DOCQA_DISABLE_DOTENV", "1")
    for key in [
        "DOCQA_LLM_API_KEY",
        "DOCQA_LLM_BASE_URL",
        "DOCQA_LLM_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(LLMConfigurationError):
        build_answer("是否规定电机噪声测试？", [])


def test_build_answer_uses_llm_for_no_evidence_refusal():
    llm = FakeLLM("没有找到足够依据回答该问题，建议补充资料或转人工复核。")
    result = build_answer("是否规定电机噪声测试？", [], llm_client=llm)

    assert "没有找到足够依据" in result["answer"]
    assert result["mode"] == "llm_grounded_refusal"
    assert "证据不足" in llm.user_prompt
    assert any(c["name"] == "no_answer_guard" for c in result["checks"])


def test_build_answer_uses_llm_for_grounded_answer():
    evidence = [
        {
            "chunk_id": "chunk-1",
            "page": 3,
            "score": 0.42,
            "kind": "text",
            "text": "键的抗拉强度应大于等于 590 MPa。",
            "source_block_ids": ["block-1"],
            "alternative_block_ids": [],
            "source_group_ids": [],
            "source_types": ["ocr_text"],
            "warnings": [],
        }
    ]
    llm = FakeLLM("根据第3页，键的抗拉强度应大于等于 590 MPa。")
    result = build_answer("键的抗拉强度要求是多少？", evidence, llm_client=llm)

    assert result["mode"] == "llm_grounded"
    assert "590 MPa" in result["answer"]
    assert "键的抗拉强度应大于等于 590 MPa" in llm.user_prompt
    llm_check = next(c for c in result["checks"] if c["name"] == "llm_judge")
    assert llm_check["status"] == "pass"


def test_answer_checks_fail_when_score_low():
    checks = answer_self_checks("问题", "当前知识库中没有找到足够依据回答该问题", [])
    score_check = next(c for c in checks if c["name"] == "evidence_score")
    assert score_check["status"] == "fail"


def test_recognition_checks_warn_on_short_text():
    checks = recognition_checks({"text": "", "average_confidence": 10, "table_regions": []})
    assert any(c["status"] == "warn" for c in checks)
