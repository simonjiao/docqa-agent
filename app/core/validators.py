from __future__ import annotations
from typing import Dict, List
import re


def recognition_checks(page: Dict) -> List[Dict]:
    text = page.get("text", "")
    avg_conf = float(page.get("average_confidence", 0) or 0)
    table_regions = page.get("table_regions", []) or []
    return [
        {
            "stage": "document_recognition",
            "name": "ocr_confidence",
            "status": "pass" if avg_conf >= 55 else "warn",
            "detail": f"平均 OCR 置信度 {avg_conf:.1f}；低于阈值时进入人工复核。",
        },
        {
            "stage": "document_recognition",
            "name": "text_density",
            "status": "pass" if len(text.strip()) >= 30 else "warn",
            "detail": f"本页识别文本长度 {len(text.strip())}。",
        },
        {
            "stage": "document_recognition",
            "name": "table_region_detection",
            "status": "pass" if table_regions else "info",
            "detail": f"检测到 {len(table_regions)} 个疑似表格区域。",
        },
    ]


def answer_self_checks(question: str, answer: str, evidence: List[Dict], min_score: float = 0.035) -> List[Dict]:
    best_score = max([item.get("score", 0.0) for item in evidence] or [0.0])
    evidence_text = "\n".join(item.get("text", "") for item in evidence)
    answer_chars = set(re.sub(r"\s+", "", answer))
    evidence_chars = set(re.sub(r"\s+", "", evidence_text))
    overlap = len(answer_chars & evidence_chars) / max(1, len(answer_chars))
    likely_no_answer = not evidence or best_score < min_score

    return [
        {
            "stage": "retrieval_validation",
            "name": "evidence_score",
            "status": "pass" if best_score >= min_score else "fail",
            "detail": f"最高检索分数 {best_score:.4f}，阈值 {min_score:.4f}。",
        },
        {
            "stage": "answer_grounding",
            "name": "answer_evidence_overlap",
            "status": "pass" if overlap >= 0.45 or likely_no_answer else "warn",
            "detail": f"答案字符可由证据覆盖比例约 {overlap:.2f}。",
        },
        {
            "stage": "answer_policy",
            "name": "no_answer_guard",
            "status": "pass" if (likely_no_answer and "没有" in answer) or not likely_no_answer else "warn",
            "detail": "证据不足时应拒答；证据充分时应给出页码/片段。",
        },
        {
            "stage": "llm_validation",
            "name": "llm_judge",
            "status": "not_configured",
            "detail": "QA 必须配置 LLM；build_answer 会将该检查更新为实际模型组织答复结果。",
        },
        {
            "stage": "human_validation",
            "name": "human_review",
            "status": "pending",
            "detail": "前端提供人工通过/退回入口，记录问题、答案、证据和复核意见。",
        },
    ]
