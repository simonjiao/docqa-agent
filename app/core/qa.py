from __future__ import annotations
from typing import Dict, List, Set
import re

from .validators import answer_self_checks
from .retrieval import normalize_for_retrieval

STOP_TERMS = {
    "本标", "标准", "规定", "什么", "多少", "是否", "该标", "要求", "哪些", "有关", "回答", "内容", "进行", "应有",
}


def _split_sentences(text: str) -> List[str]:
    text = text.replace("\n", "。")
    parts = re.split(r"(?<=[。！？.!?])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _salient_terms(question: str) -> Set[str]:
    normalized = normalize_for_retrieval(question)
    # Remove generic question scaffolding so that no-answer checks focus on
    # business terms instead of common words such as "标准" and "规定".
    for phrase in [
        "该标准", "本标准", "是否", "是不是", "有没有", "规定了", "规定",
        "要求", "是多少", "是什么", "有哪些", "哪些", "什么", "多少",
        "表1中", "表一中", "和哪些", "有关", "应有", "应该", "可以", "以及", "或者", "或",
    ]:
        normalized = normalized.replace(phrase, "")
    terms: Set[str] = set()
    for m in re.finditer(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+", normalized):
        token = m.group(0)
        if re.fullmatch(r"[a-zA-Z0-9]+", token):
            if len(token) >= 2:
                terms.add(token.lower())
            continue
        if len(token) == 1:
            terms.add(token)
        else:
            for n in (2, 3, 4):
                for i in range(0, max(0, len(token) - n + 1)):
                    terms.add(token[i:i+n])
    return {t for t in terms if t not in STOP_TERMS}


def _is_out_of_scope(question: str, evidence: List[Dict]) -> bool:
    if not evidence:
        return True
    terms = _salient_terms(question)
    if not terms:
        return False
    evidence_text = normalize_for_retrieval("\n".join(item.get("text", "") for item in evidence))
    # Require at least one salient term. For very specific questions, this blocks
    # generic hits caused by words such as "标准" or "规定".
    return not any(term in evidence_text for term in terms)


def _line_score(line: str, question: str) -> float:
    line_norm = normalize_for_retrieval(line)
    q_norm = normalize_for_retrieval(question)
    terms = _salient_terms(question)
    term_hits = sum(1 for term in terms if term in line_norm)
    char_overlap = len(set(q_norm) & set(line_norm)) / max(1, len(set(q_norm)))
    return term_hits * 2 + char_overlap


def _best_sentences(question: str, evidence: List[Dict], max_sentences: int = 3) -> List[str]:
    candidates = []
    for item in evidence:
        for sent in _split_sentences(item.get("text", "")):
            candidates.append((float(item.get("score", 0.0)) + _line_score(sent, question), sent))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    seen = set()
    result = []
    for _, sent in candidates:
        key = normalize_for_retrieval(sent)
        if key and key not in seen:
            result.append(sent)
            seen.add(key)
        if len(result) >= max_sentences:
            break
    return result


def build_answer(question: str, evidence: List[Dict]) -> Dict:
    """Extractive QA fallback with no-answer guard."""
    best_score = max([item.get("score", 0.0) for item in evidence] or [0.0])
    out_of_scope = _is_out_of_scope(question, evidence)
    if not evidence or best_score < 0.055 or out_of_scope:
        answer = "当前知识库中没有找到足够依据回答该问题，建议补充资料或转人工复核。"
        checks = answer_self_checks(question, answer, evidence, min_score=0.055)
        if out_of_scope:
            checks.insert(1, {
                "stage": "answer_policy",
                "name": "specific_term_guard",
                "status": "pass",
                "detail": "问题中的关键业务词未被证据覆盖，已触发拒答。",
            })
        return {"answer": answer, "evidence": evidence, "checks": checks, "mode": "extractive_refusal"}

    selected = evidence[:3]
    sentences = _best_sentences(question, selected)
    if not sentences:
        sentences = [selected[0]["text"][:220]]

    page_refs = "、".join(sorted({f"第{item['page']}页" for item in selected}))
    answer = f"根据{page_refs}的识别片段：" + "；".join(sentences)
    checks = answer_self_checks(question, answer, evidence, min_score=0.055)
    return {"answer": answer, "evidence": evidence, "checks": checks, "mode": "extractive_grounded"}
