from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .core.parser import process_pdf
from .core.qa import build_answer
from .core.retrieval import TfidfRetriever
from .core.schemas import Chunk
from .core.storage import (
    append_review,
    copy_sample,
    doc_dir,
    list_reviews,
    load_document,
    save_upload,
)

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent
SAMPLE_PDF = PROJECT_ROOT / "docs-for-test" / "sample_scan.pdf"

app = FastAPI(title="智能文档问答 Agent 原型", version="0.1.0")
app.mount("/static", StaticFiles(directory=APP_ROOT / "web" / "static"), name="static")

_RETRIEVERS: Dict[str, TfidfRetriever] = {}


class AskRequest(BaseModel):
    question: str
    top_k: int = 4


class ReviewRequest(BaseModel):
    question: str
    answer: str
    result: str
    notes: str = ""
    evidence: list[dict[str, Any]] = []


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html = (APP_ROOT / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    return html


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    pdf_bytes = await file.read()
    doc_id, pdf_path = save_upload(pdf_bytes, file.filename)
    result = process_pdf(doc_id, pdf_path)
    _RETRIEVERS.pop(doc_id, None)
    return result["manifest"]


@app.post("/api/load-sample")
def load_sample() -> Dict[str, Any]:
    if not SAMPLE_PDF.exists():
        raise HTTPException(status_code=404, detail="Sample PDF not found.")
    doc_id, pdf_path = copy_sample(SAMPLE_PDF)
    result = process_pdf(doc_id, pdf_path)
    _RETRIEVERS.pop(doc_id, None)
    return result["manifest"]


@app.get("/api/docs/{doc_id}")
def get_doc(doc_id: str) -> Dict[str, Any]:
    try:
        return load_document(doc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc


@app.get("/api/docs/{doc_id}/pages/{page_no}/image")
def get_page_image(doc_id: str, page_no: int) -> FileResponse:
    path = doc_dir(doc_id) / "images" / f"page-{page_no:04d}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Page image not found.")
    return FileResponse(path, media_type="image/png")


@app.get("/api/docs/{doc_id}/pages/{page_no}/recognition")
def get_page_recognition(doc_id: str, page_no: int) -> Dict[str, Any]:
    doc = load_document(doc_id)
    page_tables = [table for table in doc.get("tables", []) if table.get("page_no") == page_no]
    for page in doc["pages"]:
        if page["page_no"] == page_no:
            lines = _page_recognition_lines(doc, page_no)
            table_regions = [
                {
                    "id": element.get("raw_ref", {}).get("table_id", element["element_id"]),
                    "element_id": element["element_id"],
                    "bbox": element.get("bbox") or [0, 0, 0, 0],
                    "reason": element.get("raw_ref", {}).get("reason", "table_detection"),
                    "structured_tables": [
                        table
                        for table in page_tables
                        if table.get("region_element_id") == element["element_id"]
                    ],
                }
                for element in doc["elements"]
                if element.get("page_no") == page_no and element.get("element_type") == "table_region"
            ]
            return {
                "page": {
                    "page": page_no,
                    "page_id": page["page_id"],
                    "image_width": page["width"],
                    "image_height": page["height"],
                    "text": "\n".join(line["text"] for line in lines),
                    "lines": lines,
                    "table_regions": table_regions,
                    "tables": page_tables,
                    "average_confidence": page["average_ocr_confidence"],
                },
                "checks": page.get("checks", []),
            }
    raise HTTPException(status_code=404, detail="Page recognition not found.")


@app.get("/api/docs/{doc_id}/tables")
def list_doc_tables(doc_id: str) -> Dict[str, Any]:
    doc = load_document(doc_id)
    return {"items": doc.get("tables", [])}


@app.get("/api/docs/{doc_id}/pages/{page_no}/tables")
def list_page_tables(doc_id: str, page_no: int) -> Dict[str, Any]:
    doc = load_document(doc_id)
    return {"items": [table for table in doc.get("tables", []) if table.get("page_no") == page_no]}


@app.get("/api/docs/{doc_id}/tables/{table_id}")
def get_table(doc_id: str, table_id: str) -> Dict[str, Any]:
    doc = load_document(doc_id)
    for table in doc.get("tables", []):
        if table.get("table_id") == table_id:
            cell_ids = set(table.get("cell_ids", []))
            source_ids = cell_ids | {table.get("region_element_id"), table.get("structure_element_id")}
            return {
                "table": table,
                "elements": [item for item in doc["elements"] if item.get("element_id") in source_ids],
                "edges": [
                    edge
                    for edge in doc["edges"]
                    if edge.get("from_id") in source_ids or edge.get("to_id") in source_ids
                ],
            }
    raise HTTPException(status_code=404, detail="Table not found.")


def _page_recognition_lines(doc: Dict[str, Any], page_no: int) -> list[dict[str, Any]]:
    block_lines = [
        {
            "id": block["block_id"],
            "element_id": block["block_id"],
            "page": page_no,
            "text": block.get("text", ""),
            "bbox": block.get("bbox") or [0, 0, 0, 0],
            "confidence": block.get("confidence") or 0,
            "source_type": ",".join(block.get("source_types", [])),
            "source_group_id": ",".join(block.get("source_group_ids", [])),
            "confidence_display": _confidence_display(block.get("source_types", []), block.get("confidence")),
        }
        for block in doc["blocks"]
        if block.get("page_no") == page_no and block.get("role", "primary") == "primary"
        and "table_json" not in set(block.get("source_types", []))
    ]
    if block_lines:
        return block_lines

    return [
        {
            "id": element.get("raw_ref", {}).get("ocr_line_id", element["element_id"]),
            "element_id": element["element_id"],
            "page": page_no,
            "text": element.get("text", ""),
            "bbox": element.get("bbox") or [0, 0, 0, 0],
            "confidence": element.get("confidence") or 0,
            "source_type": element.get("source_type"),
            "source_group_id": element.get("source_group_id"),
            "confidence_display": _confidence_display([element.get("source_type")], element.get("confidence")),
        }
        for element in doc["elements"]
        if element.get("page_no") == page_no and element.get("element_type") == "ocr_text"
    ]


def _confidence_display(source_types: list[Any], confidence: Any) -> str:
    sources = {str(source_type) for source_type in source_types if source_type}
    if any("ocr" in source_type for source_type in sources):
        return f"OCR置信度 {_format_confidence(confidence)}/100"
    if "visible_text" in sources:
        return "文本层抽取"
    if "hidden_text" in sources:
        return "隐藏文本层"
    if "form_field" in sources:
        return "表单字段"
    if confidence is None:
        return "来源置信度未记录"
    return f"来源置信度 {_format_confidence(confidence)}"


def _format_confidence(confidence: Any) -> str:
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return "0"
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _get_retriever(doc_id: str) -> TfidfRetriever:
    if doc_id not in _RETRIEVERS:
        doc = load_document(doc_id)
        chunks = [Chunk(**item) for item in doc["chunks"]]
        _RETRIEVERS[doc_id] = TfidfRetriever(chunks)
    return _RETRIEVERS[doc_id]


@app.post("/api/docs/{doc_id}/ask")
def ask(doc_id: str, payload: AskRequest) -> Dict[str, Any]:
    retriever = _get_retriever(doc_id)
    evidence = retriever.search(payload.question, top_k=payload.top_k)
    result = build_answer(payload.question, evidence)
    result["question"] = payload.question
    return result


@app.post("/api/docs/{doc_id}/reviews")
def save_review(doc_id: str, payload: ReviewRequest) -> Dict[str, Any]:
    item = payload.model_dump()
    item["created_at_unix"] = int(time.time())
    item["review_id"] = f"review-{time.time_ns()}"
    item["target_chunk_ids"] = [ev.get("chunk_id") for ev in item.get("evidence", []) if ev.get("chunk_id")]
    item["target_block_ids"] = [
        block_id
        for ev in item.get("evidence", [])
        for block_id in ev.get("source_block_ids", [])
    ]
    result = append_review(doc_id, item)
    return {"ok": True, "item": result["item"], "review_edges": result["edges"]}


@app.get("/api/docs/{doc_id}/reviews")
def get_reviews(doc_id: str) -> Dict[str, Any]:
    return {"items": list_reviews(doc_id)}
