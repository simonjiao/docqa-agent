from __future__ import annotations
from typing import Dict, List
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .schemas import Chunk

DATE_TOKEN_RE = r"\d{4}\s*(?:[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}|年\s*\d{1,2}\s*月\s*\d{1,2}\s*日?)"
RELEASE_DATE_RE = re.compile(fr"(?:{DATE_TOKEN_RE}\s*发布|发布\s*[:：]?\s*{DATE_TOKEN_RE})")
IMPLEMENT_DATE_RE = re.compile(fr"(?:{DATE_TOKEN_RE}\s*实施|实施\s*[:：]?\s*{DATE_TOKEN_RE})")


def normalize_for_retrieval(text: str) -> str:
    """Normalize OCR text for retrieval.

    OCR for Chinese often inserts spaces between characters. Removing spaces and
    most punctuation makes queries such as "抗拉强度" match OCR text like
    "抗 拉 强 度".
    """
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。；：、,.!?！？\[\]（）(){}<>《》“”\"'`~|]", "", text)
    return _expand_domain_terms(text.lower())


def _expand_domain_terms(text: str) -> str:
    """Append deterministic synonyms for common document-standard questions."""
    additions = []
    mentions_standard = (
        "国家标准" in text
        or "国标" in text
        or "标准编号" in text
        or "标准号" in text
        or "标准名称" in text
        or "gb/t" in text
        or "gbt" in text
        or bool(re.search(r"\bgb\d+", text))
    )
    if mentions_standard:
        additions.append("国家标准国标标准编号标准号标准名称gb/tgbtgb")
    if "国标" in text:
        additions.append("国家标准")
    if "国家标准" in text:
        additions.append("国标")
    return text + "".join(additions)


class TfidfRetriever:
    def __init__(self, chunks: List[Chunk]):
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(2, 4),
            min_df=1,
            preprocessor=normalize_for_retrieval,
        )
        texts = [chunk.text for chunk in chunks] or [""]
        self.matrix = self.vectorizer.fit_transform(texts)

    def search(self, query: str, top_k: int = 4) -> List[Dict]:
        if not self.chunks or not query.strip():
            return []
        qv = self.vectorizer.transform([query])
        base_scores = cosine_similarity(qv, self.matrix).flatten()
        rank_scores = np.array([
            min(1.0, float(score) + _metadata_query_boost(query, chunk))
            for score, chunk in zip(base_scores, self.chunks)
        ])
        order = np.argsort(rank_scores)[::-1][:top_k]
        results = []
        for idx in order:
            score = float(rank_scores[idx])
            if score <= 0:
                continue
            chunk = self.chunks[int(idx)]
            results.append({
                "chunk_id": chunk.id,
                "page": chunk.page,
                "score": round(score, 4),
                "kind": chunk.kind,
                "text": chunk.text,
                "source_block_ids": chunk.source_block_ids,
                "alternative_block_ids": chunk.alternative_block_ids,
                "source_group_ids": chunk.source_group_ids,
                "source_types": chunk.source_types,
                "warnings": chunk.warnings,
            })
        return results


def _metadata_query_boost(query: str, chunk: Chunk) -> float:
    intent = _metadata_query_intent(query)
    text = re.sub(r"\s+", "", chunk.text)
    readable_text = re.sub(r"\s+", " ", chunk.text)
    boost = 0.0
    if intent == "release_date":
        if RELEASE_DATE_RE.search(readable_text):
            boost += 0.25
        elif "发布" in text and re.search(r"\d{4}", text):
            boost += 0.08
        if any(marker in text for marker in ["制造或出厂日期", "出厂日期", "自出厂之日起"]):
            boost -= 0.08
    elif intent == "implementation_date":
        if IMPLEMENT_DATE_RE.search(readable_text):
            boost += 0.25
        elif "实施" in text and re.search(r"\d{4}", text):
            boost += 0.08

    if chunk.page <= 2 and any(marker in text for marker in ["国家标准", "标准化管理委员会", "质量监督检验检疫"]):
        boost += 0.03
    boost += _table_query_boost(query, chunk, text)
    return boost


def _metadata_query_intent(query: str) -> str:
    compact = re.sub(r"\s+", "", query).lower()
    date_ask = any(marker in compact for marker in ["哪年", "哪一年", "年份", "日期", "时间", "什么时候"])
    if "发布" in compact and date_ask:
        return "release_date"
    if "实施" in compact and date_ask:
        return "implementation_date"
    return ""


def _table_query_boost(query: str, chunk: Chunk, compact_chunk_text: str) -> float:
    compact_query = re.sub(r"\s+", "", query).lower()
    table_intent = (
        bool(re.search(r"表(?:\d+|[一二三四五六七八九十])", compact_query))
        or "表格" in compact_query
        or "aql" in compact_query
        or "检查项目" in compact_query
        or "合格质量水平" in compact_query
    )
    if not table_intent or chunk.kind != "table":
        return 0.0

    boost = 0.16
    table_terms = ["检查项目", "键宽", "键高", "键长", "直径", "平行度", "斜度", "aql"]
    overlap = sum(1 for term in table_terms if term in compact_query and term in compact_chunk_text.lower())
    boost += min(0.12, overlap * 0.04)
    if "table_markdown" in chunk.source_types:
        boost += 0.03
    return boost
