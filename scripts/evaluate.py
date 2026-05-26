from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.parser import process_pdf
from app.core.retrieval import TfidfRetriever
from app.core.qa import build_answer
from app.core.schemas import Chunk
from app.core.storage import copy_sample, load_document

QUESTIONS = [
    {"id": "q1_scope", "question": "本标准规定了什么范围？", "expect": "正文问题"},
    {"id": "q2_strength", "question": "键的抗拉强度要求是多少？", "expect": "正文问题"},
    {"id": "q3_table", "question": "表 1 中合格质量水平 AQL 和哪些检查项目有关？", "expect": "表格问题"},
    {"id": "q4_mark", "question": "包装箱或盒外表面应有哪些标志？", "expect": "正文列表问题"},
    {"id": "q5_no_answer", "question": "该标准是否规定了电机噪声测试？", "expect": "无答案问题"},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true", help="Use bundled sample PDF.")
    parser.add_argument("--pdf", type=Path, help="Use a custom PDF.")
    args = parser.parse_args()

    if args.sample:
        pdf_path = PROJECT_ROOT / "data" / "sample" / "GBT 1568-2008 键 技术条件.pdf"
    elif args.pdf:
        pdf_path = args.pdf
    else:
        parser.error("Use --sample or --pdf <path>.")

    doc_id, stored_pdf = copy_sample(pdf_path)
    result = process_pdf(doc_id, stored_pdf)
    doc = load_document(doc_id)
    chunks = [Chunk(**item) for item in doc["chunks"]]
    retriever = TfidfRetriever(chunks)

    report = {"doc_id": doc_id, "probe": result["meta"]["probe"], "cases": []}
    for case in QUESTIONS:
        evidence = retriever.search(case["question"], top_k=4)
        answer = build_answer(case["question"], evidence)
        report["cases"].append({
            **case,
            "answer": answer["answer"],
            "evidence_pages": [item["page"] for item in answer["evidence"]],
            "checks": answer["checks"],
        })

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
