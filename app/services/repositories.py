"""Small SQLite repositories. Workflow modules use these instead of SQL directly."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from app.db import connection_scope


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


def _row_dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def create_project(name: str, project_type: str | None = None, description: str | None = None) -> dict[str, Any]:
    now = utc_now()
    project = {"id": new_id(), "name": name, "project_type": project_type, "description": description, "created_at": now, "updated_at": now}
    with connection_scope() as conn:
        conn.execute("INSERT INTO projects (id, name, project_type, description, created_at, updated_at) VALUES (:id, :name, :project_type, :description, :created_at, :updated_at)", project)
    return _decode_project(project)


def get_project(project_id: str) -> dict[str, Any] | None:
    with connection_scope() as conn:
        value = _row_dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())
    return _decode_project(value) if value else None


def update_project(project_id: str, **changes: Any) -> dict[str, Any] | None:
    allowed = {key: value for key, value in changes.items() if key in {"name", "project_type", "description", "location", "stage", "objective"}}
    if "tags" in changes:
        allowed["tags_json"] = json.dumps(changes["tags"], ensure_ascii=False)
    if not allowed:
        return get_project(project_id)
    allowed["updated_at"] = utc_now()
    allowed["id"] = project_id
    assignments = ", ".join(f"{key} = :{key}" for key in allowed if key != "id")
    with connection_scope() as conn:
        if conn.execute(f"UPDATE projects SET {assignments} WHERE id = :id", allowed).rowcount == 0:
            return None
    return get_project(project_id)


def project_exists(project_id: str) -> bool:
    return get_project(project_id) is not None


def create_document(project_id: str, file_name: str, file_type: str, path: str, parse_status: str) -> dict[str, Any]:
    value = {"id": new_id(), "project_id": project_id, "file_name": file_name, "file_type": file_type, "path": path, "parse_status": parse_status, "rag_status": None, "rag_reason": None, "indexed_chunk_count": 0, "created_at": utc_now()}
    _insert("documents", value)
    return value


def list_documents(project_id: str) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        rows = conn.execute("""SELECT d.*, COUNT(c.id) AS chunk_count FROM documents d
            LEFT JOIN source_chunks c ON c.document_id = d.id WHERE d.project_id = ?
            GROUP BY d.id ORDER BY d.rowid""", (project_id,)).fetchall()
    return [dict(row) for row in rows]


def get_document(document_id: str) -> dict[str, Any] | None:
    with connection_scope() as conn:
        return _row_dict(conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone())


def update_document_parse_status(document_id: str, parse_status: str) -> None:
    with connection_scope() as conn:
        conn.execute("UPDATE documents SET parse_status = ? WHERE id = ?", (parse_status, document_id))


def update_document_rag(document_id: str, rag_result: dict[str, Any]) -> None:
    with connection_scope() as conn:
        conn.execute("UPDATE documents SET rag_status = ?, rag_reason = ?, indexed_chunk_count = ? WHERE id = ?", (rag_result.get("rag_status"), rag_result.get("reason"), rag_result.get("indexed_count", 0), document_id))


def list_document_chunks(document_id: str) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        rows = conn.execute("SELECT id, document_id, locator, content, source_type FROM source_chunks WHERE document_id = ? ORDER BY rowid", (document_id,)).fetchall()
    return [dict(row) for row in rows]


def get_source_chunk(chunk_id: str) -> dict[str, Any] | None:
    with connection_scope() as conn:
        row = conn.execute("""SELECT c.id, c.document_id, c.locator, c.content, c.source_type, d.file_name, d.file_type
            FROM source_chunks c JOIN documents d ON d.id = c.document_id WHERE c.id = ?""", (chunk_id,)).fetchone()
    return _row_dict(row)


def delete_source_chunks(document_id: str) -> None:
    with connection_scope() as conn:
        conn.execute("DELETE FROM source_chunks WHERE document_id = ?", (document_id,))


def delete_document(document_id: str) -> bool:
    with connection_scope() as conn:
        return conn.execute("DELETE FROM documents WHERE id = ?", (document_id,)).rowcount > 0


def create_source_chunk(document_id: str, locator: str, content: str, source_type: str) -> dict[str, Any]:
    value = {"id": new_id(), "document_id": document_id, "locator": locator, "content": content, "source_type": source_type}
    _insert("source_chunks", value)
    return value


def list_source_chunks(project_id: str) -> list[dict[str, Any]]:
    """Return parseable source chunks with their document metadata for extraction."""
    with connection_scope() as conn:
        rows = conn.execute(
            """SELECT c.id, c.document_id, c.locator, c.content, c.source_type,
                      d.file_name, d.file_type, d.path, d.parse_status
               FROM source_chunks c JOIN documents d ON d.id = c.document_id
               WHERE d.project_id = ? ORDER BY d.rowid, c.rowid""",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_insight(project_id: str, category: str, title: str, content: str, sources: list[dict[str, Any]], confidence: float, review_status: str = "pending", original_ai: dict[str, Any] | None = None) -> dict[str, Any]:
    value = {"id": new_id(), "project_id": project_id, "category": category, "title": title, "content": content, "sources_json": json.dumps(sources, ensure_ascii=False), "confidence": confidence, "review_status": review_status, "original_ai_json": json.dumps(original_ai, ensure_ascii=False) if original_ai else None, "updated_at": utc_now()}
    _insert("insight_cards", value)
    return _decode_insight(value)


def list_insights(project_id: str) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        rows = conn.execute("SELECT * FROM insight_cards WHERE project_id = ? ORDER BY updated_at", (project_id,)).fetchall()
    return [_decode_insight(dict(row)) for row in rows]


def get_insight(insight_id: str) -> dict[str, Any] | None:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM insight_cards WHERE id = ?", (insight_id,)).fetchone()
    return _decode_insight(dict(row)) if row else None


def update_insight(insight_id: str, **changes: Any) -> dict[str, Any] | None:
    allowed = {key: value for key, value in changes.items() if key in {"title", "content", "category", "review_status"} and value is not None}
    if not allowed:
        return get_insight(insight_id)
    allowed["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = :{key}" for key in allowed)
    allowed["id"] = insight_id
    with connection_scope() as conn:
        cursor = conn.execute(f"UPDATE insight_cards SET {assignments} WHERE id = :id", allowed)
        if cursor.rowcount == 0:
            return None
    return get_insight(insight_id)


def create_problem(project_id: str, title: str, description: str, linked_insight_ids: list[str], evidence_status: str, priority: str, research_gap: str, status: str = "draft") -> dict[str, Any]:
    value = {"id": new_id(), "project_id": project_id, "title": title, "description": description, "linked_insight_ids_json": json.dumps(linked_insight_ids), "evidence_status": evidence_status, "priority": priority, "research_gap": research_gap, "status": status, "selected": 0, "updated_at": utc_now()}
    _insert("problem_cards", value)
    return _decode_problem(value)


def list_problems(project_id: str) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        rows = conn.execute("SELECT * FROM problem_cards WHERE project_id = ? ORDER BY rowid", (project_id,)).fetchall()
    return [_decode_problem(dict(row)) for row in rows]


def get_problem(problem_id: str) -> dict[str, Any] | None:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM problem_cards WHERE id = ?", (problem_id,)).fetchone()
    return _decode_problem(dict(row)) if row else None


def get_problem_project_id(problem_id: str) -> str | None:
    with connection_scope() as conn:
        row = conn.execute("SELECT project_id FROM problem_cards WHERE id = ?", (problem_id,)).fetchone()
    return row["project_id"] if row else None


def update_problem_selected(problem_id: str, selected: bool) -> dict[str, Any] | None:
    with connection_scope() as conn:
        cursor = conn.execute("UPDATE problem_cards SET selected = ?, updated_at = ? WHERE id = ?", (int(selected), utc_now(), problem_id))
        if cursor.rowcount == 0:
            return None
    return get_problem(problem_id)


def create_strategy(project_id: str, problem_id: str, name: str, actions: list[str], preconditions: list[str], tradeoffs: list[str], validation_items: list[str], selected: bool = False, is_custom: bool = False) -> dict[str, Any]:
    value = {"id": new_id(), "project_id": project_id, "problem_id": problem_id, "name": name, "actions_json": json.dumps(actions, ensure_ascii=False), "preconditions_json": json.dumps(preconditions, ensure_ascii=False), "tradeoffs_json": json.dumps(tradeoffs, ensure_ascii=False), "validation_items_json": json.dumps(validation_items, ensure_ascii=False), "selected": int(selected), "is_custom": int(is_custom), "updated_at": utc_now()}
    _insert("strategy_cards", value)
    return _decode_strategy(value)


def list_strategies(project_id: str) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        rows = conn.execute("SELECT * FROM strategy_cards WHERE project_id = ? ORDER BY rowid", (project_id,)).fetchall()
    return [_decode_strategy(dict(row)) for row in rows]


def get_strategy(strategy_id: str) -> dict[str, Any] | None:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM strategy_cards WHERE id = ?", (strategy_id,)).fetchone()
    return _decode_strategy(dict(row)) if row else None


def update_strategy_selected(strategy_id: str, selected: bool) -> dict[str, Any] | None:
    with connection_scope() as conn:
        row = conn.execute("SELECT problem_id FROM strategy_cards WHERE id = ?", (strategy_id,)).fetchone()
        if row is None:
            return None
        if selected:
            conn.execute("UPDATE strategy_cards SET selected = 0, updated_at = ? WHERE problem_id = ?", (utc_now(), row["problem_id"]))
        cursor = conn.execute("UPDATE strategy_cards SET selected = ?, updated_at = ? WHERE id = ?", (int(selected), utc_now(), strategy_id))
        if cursor.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM strategy_cards WHERE id = ?", (strategy_id,)).fetchone()
    return _decode_strategy(dict(row))


def update_strategy(strategy_id: str, **changes: Any) -> dict[str, Any] | None:
    allowed: dict[str, Any] = {}
    for field in ("name",):
        if field in changes and changes[field] is not None:
            allowed[field] = changes[field]
    for field in ("actions", "preconditions", "tradeoffs", "validation_items"):
        if field in changes and changes[field] is not None:
            allowed[f"{field}_json"] = json.dumps(changes[field], ensure_ascii=False)
    if not allowed:
        return get_strategy(strategy_id)
    allowed.update({"updated_at": utc_now(), "id": strategy_id})
    assignments = ", ".join(f"{field} = :{field}" for field in allowed if field != "id")
    with connection_scope() as conn:
        if conn.execute(f"UPDATE strategy_cards SET {assignments} WHERE id = :id", allowed).rowcount == 0:
            return None
    return get_strategy(strategy_id)


def delete_strategy(strategy_id: str) -> bool:
    with connection_scope() as conn:
        return conn.execute("DELETE FROM strategy_cards WHERE id = ?", (strategy_id,)).rowcount > 0


def replace_unselected_generated_strategies(problem_id: str) -> None:
    with connection_scope() as conn:
        conn.execute("DELETE FROM strategy_cards WHERE problem_id = ? AND selected = 0 AND is_custom = 0", (problem_id,))


def create_report(project_id: str, outline: list[dict[str, Any]], content: str, status: str = "draft") -> dict[str, Any]:
    now = utc_now()
    value = {"id": new_id(), "project_id": project_id, "outline_json": json.dumps(outline, ensure_ascii=False), "content": content, "status": status, "created_at": now, "updated_at": now}
    _insert("reports", value)
    return _decode_report(value)


def get_latest_report(project_id: str) -> dict[str, Any] | None:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM reports WHERE project_id = ? ORDER BY updated_at DESC LIMIT 1", (project_id,)).fetchone()
    return _decode_report(dict(row)) if row else None


def get_report(report_id: str) -> dict[str, Any] | None:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return _decode_report(dict(row)) if row else None


def update_report(report_id: str, **changes: Any) -> dict[str, Any] | None:
    allowed: dict[str, Any] = {}
    if changes.get("outline") is not None:
        allowed["outline_json"] = json.dumps(changes["outline"], ensure_ascii=False)
    for field in ("content", "status"):
        if changes.get(field) is not None:
            allowed[field] = changes[field]
    if not allowed:
        return get_report(report_id)
    allowed.update({"updated_at": utc_now(), "id": report_id})
    assignments = ", ".join(f"{field} = :{field}" for field in allowed if field != "id")
    with connection_scope() as conn:
        if conn.execute(f"UPDATE reports SET {assignments} WHERE id = :id", allowed).rowcount == 0:
            return None
    return get_report(report_id)


def create_export(project_id: str, path: str, export_id: str | None = None) -> dict[str, Any]:
    value = {"id": export_id or new_id(), "project_id": project_id, "path": path, "created_at": utc_now()}
    _insert("exports", value)
    return value


def get_export(export_id: str) -> dict[str, Any] | None:
    with connection_scope() as conn:
        return _row_dict(conn.execute("SELECT * FROM exports WHERE id = ?", (export_id,)).fetchone())


def create_task_log(project_id: str, task_type: str, status: str, message: str) -> dict[str, Any]:
    value = {"id": new_id(), "project_id": project_id, "task_type": task_type, "status": status, "message": message, "created_at": utc_now()}
    _insert("task_logs", value)
    return value


def list_task_logs(project_id: str) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        rows = conn.execute("SELECT * FROM task_logs WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
    return [dict(row) for row in rows]


def _insert(table: str, value: dict[str, Any]) -> None:
    columns = ", ".join(value)
    placeholders = ", ".join(f":{key}" for key in value)
    with connection_scope() as conn:
        conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", value)


def _list(table: str, project_id: str) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE project_id = ? ORDER BY rowid", (project_id,)).fetchall()]


def _decode_insight(value: dict[str, Any]) -> dict[str, Any]:
    value = value.copy()
    value["sources"] = json.loads(value.pop("sources_json"))
    value.pop("project_id", None)
    value.pop("original_ai_json", None)
    value.pop("updated_at", None)
    return value


def _decode_project(value: dict[str, Any]) -> dict[str, Any]:
    value = value.copy()
    value["tags"] = json.loads(value.pop("tags_json", None) or "[]")
    return value


def _decode_problem(value: dict[str, Any]) -> dict[str, Any]:
    value = value.copy()
    value["linked_insight_ids"] = json.loads(value.pop("linked_insight_ids_json"))
    value.pop("project_id", None)
    value["selected"] = bool(value.get("selected", 0))
    return value


def _decode_strategy(value: dict[str, Any]) -> dict[str, Any]:
    value = value.copy()
    for field in ("actions", "preconditions", "tradeoffs", "validation_items"):
        value[field] = json.loads(value.pop(f"{field}_json"))
    value["selected"] = bool(value["selected"])
    value["is_custom"] = bool(value.get("is_custom", 0))
    value.pop("project_id", None)
    return value


def _decode_report(value: dict[str, Any]) -> dict[str, Any]:
    value = value.copy()
    value["outline"] = json.loads(value.pop("outline_json"))
    return value
