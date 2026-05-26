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
SAMPLE_PDF = PROJECT_ROOT / "data" / "sample" / "GBT 1568-2008 键 技术条件.pdf"

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
    return result["meta"]


@app.post("/api/load-sample")
def load_sample() -> Dict[str, Any]:
    if not SAMPLE_PDF.exists():
        raise HTTPException(status_code=404, detail="Sample PDF not found.")
    doc_id, pdf_path = copy_sample(SAMPLE_PDF)
    result = process_pdf(doc_id, pdf_path)
    _RETRIEVERS.pop(doc_id, None)
    return result["meta"]


@app.get("/api/docs/{doc_id}")
def get_doc(doc_id: str) -> Dict[str, Any]:
    try:
        return load_document(doc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc


@app.get("/api/docs/{doc_id}/pages/{page_no}/image")
def get_page_image(doc_id: str, page_no: int) -> FileResponse:
    path = doc_dir(doc_id) / "pages" / f"page-{page_no}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Page image not found.")
    return FileResponse(path, media_type="image/png")


@app.get("/api/docs/{doc_id}/pages/{page_no}/recognition")
def get_page_recognition(doc_id: str, page_no: int) -> Dict[str, Any]:
    doc = load_document(doc_id)
    for page in doc["pages"]:
        if page["page"] == page_no:
            return {
                "page": page,
                "checks": doc["meta"].get("recognition_checks", {}).get(str(page_no), []),
            }
    raise HTTPException(status_code=404, detail="Page recognition not found.")


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
    append_review(doc_id, item)
    return {"ok": True, "item": item}


@app.get("/api/docs/{doc_id}/reviews")
def get_reviews(doc_id: str) -> Dict[str, Any]:
    return {"items": list_reviews(doc_id)}
