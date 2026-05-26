from app.core.qa import build_answer
from app.core.validators import answer_self_checks, recognition_checks


def test_build_answer_refuses_without_evidence():
    result = build_answer("是否规定电机噪声测试？", [])
    assert "没有找到足够依据" in result["answer"]
    assert any(c["name"] == "no_answer_guard" for c in result["checks"])


def test_answer_checks_fail_when_score_low():
    checks = answer_self_checks("问题", "当前知识库中没有找到足够依据回答该问题", [])
    score_check = next(c for c in checks if c["name"] == "evidence_score")
    assert score_check["status"] == "fail"


def test_recognition_checks_warn_on_short_text():
    checks = recognition_checks({"text": "", "average_confidence": 10, "table_regions": []})
    assert any(c["status"] == "warn" for c in checks)
