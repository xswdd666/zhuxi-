"""SQLite bootstrap and connection helpers for the one-day MVP."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "zhuxi_mvp.sqlite3"
UPLOADS_DIR = PROJECT_ROOT / "uploads"
OUTPUT_DIR = PROJECT_ROOT / "output"
STATIC_DIR = Path(__file__).resolve().parent / "static"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    project_type TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    location TEXT,
    stage TEXT,
    objective TEXT,
    tags_json TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    path TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    rag_status TEXT,
    rag_reason TEXT,
    indexed_chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    locator TEXT NOT NULL,
    content TEXT NOT NULL,
    source_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS insight_cards (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    review_status TEXT NOT NULL,
    original_ai_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS problem_cards (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    linked_insight_ids_json TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    priority TEXT NOT NULL,
    research_gap TEXT NOT NULL,
    status TEXT NOT NULL,
    selected INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS strategy_cards (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    problem_id TEXT NOT NULL REFERENCES problem_cards(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    actions_json TEXT NOT NULL,
    preconditions_json TEXT NOT NULL,
    tradeoffs_json TEXT NOT NULL,
    validation_items_json TEXT NOT NULL,
    selected INTEGER NOT NULL DEFAULT 0,
    is_custom INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    outline_json TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_logs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_insights_project_id ON insight_cards(project_id);
CREATE INDEX IF NOT EXISTS idx_problems_project_id ON problem_cards(project_id);
CREATE INDEX IF NOT EXISTS idx_strategies_project_id ON strategy_cards(project_id);
CREATE INDEX IF NOT EXISTS idx_reports_project_id ON reports(project_id);
"""


# SQLite CREATE TABLE IF NOT EXISTS does not evolve installations that were
# created by earlier MVP builds.  Keep these additive migrations idempotent so
# user projects are retained across upgrades.
ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "projects": {
        "location": "TEXT",
        "stage": "TEXT",
        "objective": "TEXT",
        "tags_json": "TEXT",
        "updated_at": "TEXT",
    },
    "problem_cards": {
        "selected": "INTEGER NOT NULL DEFAULT 0",
        "updated_at": "TEXT",
    },
    "strategy_cards": {
        "is_custom": "INTEGER NOT NULL DEFAULT 0",
        "updated_at": "TEXT",
    },
    "documents": {
        "rag_status": "TEXT",
        "rag_reason": "TEXT",
        "indexed_chunk_count": "INTEGER NOT NULL DEFAULT 0",
    },
}


def run_additive_migrations(connection: sqlite3.Connection) -> None:
    """Add known MVP columns without deleting or rewriting existing records."""
    for table, columns in ADDITIVE_COLUMNS.items():
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def initialize_database() -> None:
    """Create runtime folders, database file, and all MVP tables idempotently."""
    for directory in (DATA_DIR, UPLOADS_DIR, OUTPUT_DIR, STATIC_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    connection = get_connection()
    try:
        connection.executescript(SCHEMA_SQL)
        run_additive_migrations(connection)
        connection.commit()
    finally:
        connection.close()


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def connection_scope() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
