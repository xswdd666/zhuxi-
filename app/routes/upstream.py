"""Upload, source parsing, insight generation, and human review endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from app.agents.extractor import extract_insights
from app.schemas import Document, Insight, InsightUpdate
from app.services import parser, rag, repositories


router = APIRouter(prefix="/api")


def _document_response(document: dict[str, Any]) -> dict[str, Any]:
    """Return public document metadata; storage paths are server-only."""
    return {key: value for key, value in document.items() if key != "path"}


def _project_or_404(project_id: str) -> None:
    if not repositories.project_exists(project_id):
        raise HTTPException(status_code=404, detail="项目不存在。")


@router.post("/projects/{project_id}/documents", response_model=dict)
async def upload_documents(project_id: str, files: Annotated[list[UploadFile], File(...)]) -> dict[str, Any]:
    _project_or_404(project_id)
    documents = []
    for upload in files:
        try:
            stored_path, file_type, display_name = await parser.save_upload(project_id, upload)
            document = repositories.create_document(project_id, display_name, file_type, str(stored_path), "saved")
            status, chunks = parser.parse_file(stored_path, file_type)
            repositories.update_document_parse_status(document["id"], status)
            document["parse_status"] = status
            indexed_chunks = []
            for locator, content, source_type in chunks:
                chunk = repositories.create_source_chunk(document["id"], locator, content, source_type)
                indexed_chunks.append({**chunk, "file_name": document["file_name"]})
            document["rag"] = rag.index_project_chunks(project_id, indexed_chunks)
            repositories.update_document_rag(document["id"], document["rag"])
            document.update({"rag_status": document["rag"]["rag_status"], "rag_reason": document["rag"].get("reason"), "indexed_chunk_count": document["rag"].get("indexed_count", 0), "chunk_count": len(chunks)})
            documents.append(_document_response(document))
        except Exception as exc:
            # A bad item must not discard other files in this multipart request.
            display_name = parser.safe_filename(upload.filename)
            documents.append({"file_name": display_name, "file_type": Path(display_name).suffix.lstrip(".") or "unknown", "parse_status": f"upload_failed: {type(exc).__name__}", "rag_status": "degraded", "rag_reason": "文件保存或解析失败。", "indexed_chunk_count": 0, "chunk_count": 0})
    statuses = [document.get("rag", {"rag_status": document.get("rag_status", "degraded"), "reason": document.get("rag_reason")}) for document in documents]
    return {
        "documents": documents,
        "rag_status": "degraded" if any(status["rag_status"] == "degraded" for status in statuses) else "ready",
        "rag": statuses,
    }


@router.get("/projects/{project_id}/documents", response_model=dict[str, list[Document]])
def list_documents(project_id: str) -> dict[str, list[dict[str, Any]]]:
    _project_or_404(project_id)
    return {"documents": [_document_response(item) for item in repositories.list_documents(project_id)]}


def _document_or_404(document_id: str) -> dict[str, Any]:
    document = repositories.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文件不存在。")
    return document


@router.get("/documents/{document_id}/chunks", response_model=dict)
def list_document_chunks(document_id: str) -> dict[str, Any]:
    document = _document_or_404(document_id)
    return {"document": _document_response(document), "chunks": repositories.list_document_chunks(document_id)}


@router.get("/source-chunks/{chunk_id}", response_model=dict)
def read_source_chunk(chunk_id: str) -> dict[str, Any]:
    chunk = repositories.get_source_chunk(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="来源片段不存在。")
    return {"source_chunk": chunk}


@router.get("/documents/{document_id}/preview", response_model=None)
def preview_document(document_id: str) -> FileResponse | PlainTextResponse:
    document = _document_or_404(document_id)
    stored_path = Path(document["path"])
    if not stored_path.is_file():
        raise HTTPException(status_code=404, detail="原始文件已不可用。")
    if document["file_type"] in {"txt", "md", "markdown"}:
        try:
            return PlainTextResponse(stored_path.read_text(encoding="utf-8-sig"))
        except UnicodeDecodeError:
            return PlainTextResponse(stored_path.read_text(encoding="gb18030"))
    media_types = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
    }
    return FileResponse(stored_path, media_type=media_types.get(document["file_type"], "application/octet-stream"))


@router.post("/documents/{document_id}/retry", response_model=dict)
def retry_document(document_id: str) -> dict[str, Any]:
    document = _document_or_404(document_id)
    stored_path = Path(document["path"])
    if not stored_path.is_file():
        raise HTTPException(status_code=404, detail="原始文件已不可用，无法重新解析。")
    rag.delete_document_vectors(document_id)
    repositories.delete_source_chunks(document_id)
    status, chunks = parser.parse_file(stored_path, document["file_type"])
    repositories.update_document_parse_status(document_id, status)
    indexed_chunks = []
    for locator, content, source_type in chunks:
        chunk = repositories.create_source_chunk(document_id, locator, content, source_type)
        indexed_chunks.append({**chunk, "file_name": document["file_name"]})
    rag_result = rag.index_project_chunks(document["project_id"], indexed_chunks)
    repositories.update_document_rag(document_id, rag_result)
    refreshed = _document_or_404(document_id)
    refreshed.update({"chunk_count": len(chunks), "rag": rag_result})
    return {"document": _document_response(refreshed), "message": "文件已重新解析。"}


@router.delete("/documents/{document_id}", response_model=dict)
def delete_document(document_id: str) -> dict[str, Any]:
    document = _document_or_404(document_id)
    references = [insight for insight in repositories.list_insights(document["project_id"])
                  if any(source.get("document_id") == document_id for source in insight["sources"])]
    if references:
        raise HTTPException(status_code=409, detail={"code": "DOCUMENT_IN_USE", "message": "该文件已被洞察引用，不能直接删除。", "details": {"reference_count": len(references)}})
    rag_result = rag.delete_document_vectors(document_id)
    repositories.delete_document(document_id)
    stored_path = Path(document["path"])
    if stored_path.is_file():
        stored_path.unlink()
    return {"deleted": True, "document_id": document_id, "rag": rag_result}


@router.post("/projects/{project_id}/insights:generate", response_model=dict)
def generate_insights(project_id: str) -> dict[str, Any]:
    _project_or_404(project_id)
    chunks = repositories.list_source_chunks(project_id)
    proposed, mode, message = extract_insights(chunks)
    if not proposed:
        raise HTTPException(status_code=503, detail={"code": "MODEL_UNAVAILABLE", "message": message or "无法生成洞察。"})
    chunk_index = {chunk["id"]: chunk for chunk in chunks}
    existing = {
        (item["title"], item["content"], source.get("document_id"))
        for item in repositories.list_insights(project_id)
        for source in item["sources"]
    }
    insights = []
    skipped_count = 0
    for item in proposed:
        chunk = chunk_index.get(item.get("source_chunk_id"))
        if not chunk:
            continue
        is_image = chunk["source_type"] == "image"
        observation = item.get("observation") or (item["content"] if is_image else None)
        quote = observation if is_image else _quote_for(item["content"], chunk["content"])
        source = {
            "source_chunk_id": chunk["id"], "document_id": chunk["document_id"], "file_name": chunk["file_name"],
            "locator": chunk["locator"], "quote": quote,
            "source_type": "image_observation" if is_image else "text_excerpt",
            "observation": observation,
        }
        if (item["title"], item["content"], chunk["document_id"]) in existing:
            skipped_count += 1
            continue
        insights.append(repositories.create_insight(project_id, item["category"], item["title"], item["content"], [source], item["confidence"], "pending", item))
    return {"insights": insights, "created_count": len(insights), "skipped_count": skipped_count, "mode": mode, "message": message}


@router.get("/projects/{project_id}/task-logs", response_model=dict)
def list_task_logs(project_id: str) -> dict[str, Any]:
    _project_or_404(project_id)
    return {"logs": repositories.list_task_logs(project_id)}


@router.get("/projects/{project_id}/insights", response_model=dict[str, list[Insight]])
def list_insights(project_id: str) -> dict[str, list[dict[str, Any]]]:
    _project_or_404(project_id)
    return {"insights": repositories.list_insights(project_id)}


@router.patch("/insights/{insight_id}", response_model=Insight)
def review_insight(insight_id: str, payload: InsightUpdate) -> dict[str, Any]:
    insight = repositories.get_insight(insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail="洞察卡不存在。")
    changes = payload.model_dump(exclude_unset=True)
    new_category = changes.get("category", insight["category"])
    new_status = changes.get("review_status", insight["review_status"])
    if new_status == "confirmed" and new_category in {"site_fact", "design_constraint"} and not insight["sources"]:
        raise HTTPException(status_code=422, detail="无可定位来源的事实或约束不能确认，请改为信息缺口或补充来源。")
    updated = repositories.update_insight(insight_id, **changes)
    assert updated is not None
    return updated


def _quote_for(content: str, source: str) -> str:
    normalized = content.strip()
    position = source.find(normalized)
    if position >= 0:
        return source[position : position + min(len(normalized), 300)]
    return source[:300].strip()
