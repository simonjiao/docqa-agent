import pytest
import json

from app.core.qa import LLMConfigurationError, build_answer
from app.core.validators import answer_self_checks, recognition_checks


class FakeLLM:
    model = "fake-test-model"

    def __init__(self, answer: str):
        self.answer = answer
        self.system_prompt = ""
        self.user_prompt = ""

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
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


def test_build_answer_treats_national_standard_alias_as_grounded():
    evidence = [
        {
            "chunk_id": "cover",
            "page": 1,
            "score": 0.2,
            "kind": "text",
            "text": "中华人民共和国国家标准\nGB/T 1568—2008\n键 技术条件",
            "source_block_ids": ["cover-block"],
            "alternative_block_ids": [],
            "source_group_ids": [],
            "source_types": ["image_ocr"],
            "warnings": [],
        }
    ]
    llm = FakeLLM("根据第1页，这是 GB/T 1568—2008《键 技术条件》。")
    result = build_answer("这是什么国标", evidence, llm_client=llm)

    assert result["mode"] == "llm_grounded"
    assert "证据初步可用" in llm.user_prompt


def test_build_answer_defaults_ellipsis_to_current_document():
    evidence = [
        {
            "chunk_id": "release",
            "page": 1,
            "score": 0.31,
            "kind": "text",
            "text": "Technical specifications for keys\n2008-09-22 发布 2009-05-01 实施\n中华人民共和国国家质量监督检验检疫总局发布",
            "source_block_ids": ["release-block"],
            "alternative_block_ids": [],
            "source_group_ids": [],
            "source_types": ["image_ocr"],
            "warnings": [],
        }
    ]
    llm = FakeLLM("根据第1页，该标准于 2008 年发布，发布日期为 2008-09-22。")
    result = build_answer("哪一年发布的", evidence, llm_client=llm)

    assert result["mode"] == "llm_grounded"
    assert "默认指当前文档或当前标准" in llm.system_prompt
    assert "不要因为问题省略" in llm.user_prompt


def test_build_answer_formats_table_json_for_llm_prompt():
    table = {
        "table_id": "p0004-t0001",
        "status": "needs_review",
        "strategy": "scanned_ocr_table",
        "row_count": 3,
        "column_count": 2,
        "headers": ["检查 项 目", "平 键"],
        "rows": [
            {"cells": {"检查 项 目": "键 宽", "平 键": "1.0"}},
            {"cells": {"检查 项 目": "键 高", "平 键": "2.5"}},
        ],
    }
    evidence = [
        {
            "chunk_id": "table-json",
            "page": 4,
            "score": 0.25,
            "kind": "table",
            "text": json.dumps(table, ensure_ascii=False),
            "source_block_ids": ["table-block"],
            "alternative_block_ids": [],
            "source_group_ids": [],
            "source_types": ["table_cell", "table_json", "table_structure"],
            "warnings": ["table_needs_review"],
        }
    ]
    llm = FakeLLM("根据第4页表格，检查项目包括键宽和键高。")

    result = build_answer("表1中检查项目有哪些？", evidence, llm_client=llm)

    assert result["mode"] == "llm_grounded"
    assert "表格 p0004-t0001" in llm.user_prompt
    assert "| 键 高 | 2.5 |" in llm.user_prompt


def test_answer_checks_fail_when_score_low():
    checks = answer_self_checks("问题", "当前知识库中没有找到足够依据回答该问题", [])
    score_check = next(c for c in checks if c["name"] == "evidence_score")
    assert score_check["status"] == "fail"


def test_recognition_checks_warn_on_short_text():
    checks = recognition_checks({"text": "", "average_confidence": 10, "table_regions": []})
    assert any(c["status"] == "warn" for c in checks)
