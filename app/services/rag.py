"""Minimal local RAG backed by Ollama embeddings and persistent ChromaDB."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.db import PROJECT_ROOT


COLLECTION_NAME = "zhuxi_source_chunks"
EMBEDDING_DIMENSIONS = 1024


class RagUnavailable(RuntimeError):
    """Raised when the optional vector path cannot serve a request."""


def _settings() -> tuple[str, str, Path, float]:
    ollama_url = os.getenv("OLLAMA_EMBED_URL", "http://127.0.0.1:11434/api/embed")
    model = os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")
    chroma_dir = Path(os.getenv("CHROMA_DIR", str(PROJECT_ROOT / "data" / "chroma")))
    timeout = float(os.getenv("OLLAMA_EMBED_TIMEOUT_SECONDS", "20"))
    return ollama_url, model, chroma_dir, timeout


def _embed(inputs: list[str]) -> list[list[float]]:
    url, model, _, timeout = _settings()
    payload = json.dumps({"model": model, "input": inputs}).encode("utf-8")
    request = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local Ollama URL is configurable by operator
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RagUnavailable(f"Ollama embedding unavailable: {type(exc).__name__}") from exc

    embeddings = body.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(inputs):
        raise RagUnavailable("Ollama returned an invalid embedding response")
    if any(not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSIONS for vector in embeddings):
        raise RagUnavailable(f"Ollama embedding dimension must be {EMBEDDING_DIMENSIONS}")
    return embeddings


def _collection() -> Any:
    try:
        import chromadb

        _, _, chroma_dir, _ = _settings()
        chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(chroma_dir))
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception as exc:
        raise RagUnavailable(f"Chroma unavailable: {type(exc).__name__}") from exc


def index_project_chunks(project_id: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Embed and persist parsed chunks. SQLite remains the source of truth on failure."""
    text_chunks = [chunk for chunk in chunks if chunk.get("source_type") == "text" and chunk.get("content", "").strip()]
    if not text_chunks:
        return {"rag_status": "ready", "indexed_count": 0, "embedding_dimensions": EMBEDDING_DIMENSIONS}
    try:
        embeddings = _embed([chunk["content"] for chunk in text_chunks])
        collection = _collection()
        collection.upsert(
            ids=[chunk["id"] for chunk in text_chunks],
            embeddings=embeddings,
            documents=[chunk["content"] for chunk in text_chunks],
            metadatas=[
                {
                    "project_id": project_id,
                    "document_id": chunk["document_id"],
                    "file_name": chunk["file_name"],
                    "locator": chunk["locator"],
                    "source_type": chunk["source_type"],
                }
                for chunk in text_chunks
            ],
        )
        return {"rag_status": "ready", "indexed_count": len(text_chunks), "embedding_dimensions": EMBEDDING_DIMENSIONS}
    except RagUnavailable as exc:
        return {"rag_status": "degraded", "indexed_count": 0, "reason": str(exc)}
    except Exception as exc:
        return {"rag_status": "degraded", "indexed_count": 0, "reason": f"RAG indexing failed: {type(exc).__name__}"}


def delete_document_vectors(document_id: str) -> dict[str, Any]:
    """Best-effort Chroma cleanup; SQLite/file deletion remains authoritative."""
    try:
        _collection().delete(where={"document_id": document_id})
        return {"rag_status": "ready"}
    except Exception as exc:
        return {"rag_status": "degraded", "reason": f"RAG vector cleanup failed: {type(exc).__name__}"}


def retrieve_project_context(project_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
    """Retrieve project-isolated vector context, or explicit SQLite raw-chunk fallback."""
    limit = max(1, top_k)
    try:
        embedding = _embed([query])[0]
        response = _collection().query(
            query_embeddings=[embedding],
            n_results=limit,
            where={"project_id": project_id},
            include=["documents", "metadatas", "distances"],
        )
        documents = (response.get("documents") or [[]])[0]
        metadata = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        results = [
            {
                "content": content,
                "file_name": item["file_name"],
                "locator": item["locator"],
                "document_id": item["document_id"],
                "source_type": item["source_type"],
                "distance": distance,
            }
            for content, item, distance in zip(documents, metadata, distances)
        ]
        return {"rag_status": "ready", "retrieval_source": "chroma_vector", "results": results}
    except Exception as exc:
        # This is intentionally raw SQLite fallback, not vector retrieval or keyword search.
        from app.services import repositories

        raw_chunks = repositories.list_source_chunks(project_id)
        text_chunks = [chunk for chunk in raw_chunks if chunk["source_type"] == "text"]
        results = [
            {
                "content": chunk["content"],
                "file_name": chunk["file_name"],
                "locator": chunk["locator"],
                "document_id": chunk["document_id"],
                "source_type": chunk["source_type"],
                "distance": None,
            }
            for chunk in text_chunks[:limit]
        ]
        reason = str(exc) if isinstance(exc, RagUnavailable) else f"RAG retrieval failed: {type(exc).__name__}"
        return {"rag_status": "degraded", "retrieval_source": "sqlite_raw_chunks", "reason": reason, "results": results}
