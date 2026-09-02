"""Pydantic contracts shared by the API and future workflow modules."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_type: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    project_type: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    location: str | None = Field(default=None, max_length=200)
    stage: str | None = Field(default=None, max_length=100)
    objective: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = Field(default=None, max_length=20)


class Project(BaseModel):
    id: str
    name: str
    project_type: str | None = None
    description: str | None = None
    location: str | None = None
    stage: str | None = None
    objective: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class Source(BaseModel):
    source_chunk_id: str | None = None
    document_id: str
    file_name: str
    locator: str
    quote: str
    source_type: str | None = None
    observation: str | None = None


class Document(BaseModel):
    id: str
    project_id: str
    file_name: str
    file_type: str
    parse_status: str
    rag_status: str | None = None
    rag_reason: str | None = None
    indexed_chunk_count: int = 0
    chunk_count: int = 0
    created_at: datetime


class Insight(BaseModel):
    id: str
    category: Literal["site_fact", "design_constraint", "user_need", "information_gap"]
    title: str
    content: str
    sources: list[Source]
    confidence: float = Field(ge=0, le=1)
    review_status: Literal["pending", "confirmed", "edited", "rejected", "needs_verification"]


class InsightUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    content: str | None = Field(default=None, min_length=1)
    category: Literal["site_fact", "design_constraint", "user_need", "information_gap"] | None = None
    review_status: Literal["pending", "confirmed", "edited", "rejected", "needs_verification"]


class Problem(BaseModel):
    id: str
    title: str
    description: str
    linked_insight_ids: list[str]
    evidence_status: Literal["confirmed", "hypothesis"]
    priority: Literal["low", "medium", "high"]
    research_gap: str
    status: Literal["draft", "ready", "rejected"]
    selected: bool = False


class ProblemUpdate(BaseModel):
    selected: bool


class Strategy(BaseModel):
    id: str
    problem_id: str
    name: str
    actions: list[str]
    preconditions: list[str]
    tradeoffs: list[str]
    validation_items: list[str]
    selected: bool = False
    is_custom: bool = False


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    actions: list[str] = Field(min_length=1, max_length=8)
    preconditions: list[str] = Field(min_length=1, max_length=8)
    tradeoffs: list[str] = Field(min_length=1, max_length=8)
    validation_items: list[str] = Field(min_length=1, max_length=8)


class StrategyUpdate(BaseModel):
    selected: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    actions: list[str] | None = Field(default=None, min_length=1, max_length=8)
    preconditions: list[str] | None = Field(default=None, min_length=1, max_length=8)
    tradeoffs: list[str] | None = Field(default=None, min_length=1, max_length=8)
    validation_items: list[str] | None = Field(default=None, min_length=1, max_length=8)


class MarkdownExport(BaseModel):
    id: str
    project_id: str
    filename: str
    content: str
    created_at: datetime


class ReportSection(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=120)
    visible: bool = True


class Report(BaseModel):
    id: str
    project_id: str
    outline: list[ReportSection]
    content: str
    status: str
    created_at: datetime
    updated_at: datetime


class ReportUpdate(BaseModel):
    outline: list[ReportSection] | None = Field(default=None, min_length=1, max_length=12)
    content: str | None = Field(default=None, min_length=1, max_length=50000)
    status: str | None = Field(default=None, min_length=1, max_length=40)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody
