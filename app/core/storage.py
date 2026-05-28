from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import hashlib
import json
import os
import shutil

from .schemas import BlockArtifact, Chunk, EdgeArtifact, ElementArtifact, PageArtifact


def storage_root() -> Path:
    return Path(os.getenv("STORAGE_DIR", "./storage")).resolve()


def make_doc_id(pdf_bytes: bytes, filename: str) -> str:
    digest = hashlib.sha256(pdf_bytes + filename.encode("utf-8", errors="ignore")).hexdigest()[:16]
    safe = "".join(ch for ch in Path(filename).stem if ch.isalnum() or ch in "-_")[:32] or "doc"
    return f"{safe}-{digest}"


def doc_dir(doc_id: str) -> Path:
    return storage_root() / doc_id


def save_upload(pdf_bytes: bytes, filename: str) -> tuple[str, Path]:
    doc_id = make_doc_id(pdf_bytes, filename)
    root = doc_dir(doc_id)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    pdf_path = root / "raw" / "source.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)
    return doc_id, pdf_path


def copy_sample(sample_path: Path) -> tuple[str, Path]:
    data = sample_path.read_bytes()
    doc_id, pdf_path = save_upload(data, sample_path.name)
    return doc_id, pdf_path


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, items: List[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            if hasattr(item, "to_dict"):
                item = item.to_dict()
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_document(
    doc_id: str,
    manifest: Dict[str, Any],
    pages: List[PageArtifact],
    elements: List[ElementArtifact],
    edges: List[EdgeArtifact],
    blocks: List[BlockArtifact],
    chunks: List[Chunk],
) -> None:
    root = doc_dir(doc_id)
    write_json(root / "manifest.json", manifest)
    write_jsonl(root / "pages.jsonl", pages)
    write_jsonl(root / "elements.jsonl", elements)
    write_jsonl(root / "edges.jsonl", edges)
    write_jsonl(root / "blocks.jsonl", blocks)
    write_jsonl(root / "chunks.jsonl", chunks)


def load_document(doc_id: str) -> Dict[str, Any]:
    root = doc_dir(doc_id)
    return {
        "manifest": read_json(root / "manifest.json"),
        "pages": read_jsonl(root / "pages.jsonl"),
        "elements": read_jsonl(root / "elements.jsonl"),
        "edges": read_jsonl(root / "edges.jsonl"),
        "blocks": read_jsonl(root / "blocks.jsonl"),
        "chunks": read_jsonl(root / "chunks.jsonl"),
    }


def append_review(doc_id: str, item: Dict[str, Any]) -> None:
    root = doc_dir(doc_id)
    path = root / "reviews.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def list_reviews(doc_id: str) -> List[Dict[str, Any]]:
    return read_jsonl(doc_dir(doc_id) / "reviews.jsonl")


def clean_storage() -> None:
    root = storage_root()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
