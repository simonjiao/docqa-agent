from __future__ import annotations
from typing import Dict, List
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .schemas import Chunk


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
        scores = cosine_similarity(qv, self.matrix).flatten()
        order = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in order:
            score = float(scores[idx])
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
