"""Regression coverage for the Stage A safety fixes."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db
from app.services import rag


class RetrieveProjectContextTests(unittest.TestCase):
    def test_vector_result_is_returned_without_sqlite_fallback(self) -> None:
        class Collection:
            def query(self, **_: object) -> dict[str, list[list[object]]]:
                return {
                    "documents": [["riverfront access is constrained"]],
                    "metadatas": [[{
                        "file_name": "brief.md", "locator": "line 8",
                        "document_id": "document-1", "source_type": "text",
                    }]],
                    "distances": [[0.12]],
                }

        with patch.object(rag, "_embed", return_value=[[0.0] * rag.EMBEDDING_DIMENSIONS]), patch.object(rag, "_collection", return_value=Collection()):
            result = rag.retrieve_project_context("project-1", "access constraints")

        self.assertEqual(result["rag_status"], "ready")
        self.assertEqual(result["retrieval_source"], "chroma_vector")
        self.assertEqual(result["results"][0]["file_name"], "brief.md")

    def test_unavailable_vector_service_uses_text_sqlite_chunks(self) -> None:
        raw_chunks = [
            {"content": "image bytes", "file_name": "site.png", "locator": "image", "document_id": "doc-image", "source_type": "image"},
            {"content": "verified source text", "file_name": "brief.md", "locator": "line 2", "document_id": "doc-text", "source_type": "text"},
        ]
        with patch.object(rag, "_embed", side_effect=rag.RagUnavailable("offline")), patch("app.services.repositories.list_source_chunks", return_value=raw_chunks):
            result = rag.retrieve_project_context("project-1", "brief")

        self.assertEqual(result["rag_status"], "degraded")
        self.assertEqual(result["retrieval_source"], "sqlite_raw_chunks")
        self.assertEqual(result["results"], [{
            "content": "verified source text", "file_name": "brief.md", "locator": "line 2",
            "document_id": "doc-text", "source_type": "text", "distance": None,
        }])


class DatabaseMigrationTests(unittest.TestCase):
    def test_existing_database_gains_columns_without_losing_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = root / "legacy.sqlite3"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, project_type TEXT, description TEXT, created_at TEXT NOT NULL)")
                connection.execute("INSERT INTO projects VALUES ('old-project', '旧项目', NULL, NULL, '2026-01-01T00:00:00+00:00')")
                connection.execute("CREATE TABLE problem_cards (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL, linked_insight_ids_json TEXT NOT NULL, evidence_status TEXT NOT NULL, priority TEXT NOT NULL, research_gap TEXT NOT NULL, status TEXT NOT NULL)")
                connection.execute("CREATE TABLE strategy_cards (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, problem_id TEXT NOT NULL, name TEXT NOT NULL, actions_json TEXT NOT NULL, preconditions_json TEXT NOT NULL, tradeoffs_json TEXT NOT NULL, validation_items_json TEXT NOT NULL, selected INTEGER NOT NULL DEFAULT 0)")
                connection.commit()
            finally:
                connection.close()

            with patch.object(db, "DATABASE_PATH", database_path), patch.object(db, "DATA_DIR", root / "data"), patch.object(db, "UPLOADS_DIR", root / "uploads"), patch.object(db, "OUTPUT_DIR", root / "output"), patch.object(db, "STATIC_DIR", root / "static"):
                db.initialize_database()
                db.initialize_database()  # idempotent on a subsequent service start
                connection = db.get_connection()
                try:
                    project_columns = {row["name"] for row in connection.execute("PRAGMA table_info(projects)")}
                    strategy_columns = {row["name"] for row in connection.execute("PRAGMA table_info(strategy_cards)")}
                    saved = connection.execute("SELECT name FROM projects WHERE id = 'old-project'").fetchone()
                    report_table = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'reports'").fetchone()
                finally:
                    connection.close()

            self.assertTrue({"location", "stage", "objective", "tags_json", "updated_at"}.issubset(project_columns))
            self.assertTrue({"is_custom", "updated_at"}.issubset(strategy_columns))
            self.assertEqual(saved["name"], "旧项目")
            self.assertIsNotNone(report_table)


if __name__ == "__main__":
    unittest.main()
