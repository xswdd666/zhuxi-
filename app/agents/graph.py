"""Controlled sequential workflow; LangGraph is intentionally optional for MVP reliability."""

from __future__ import annotations

from typing import Any, Callable

from app.agents.diagnostician import generate_problems
from app.agents.strategist import generate_strategies
from app.services import repositories


def run_problems(project_id: str, insights: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, str | None]:
    return _run_node(project_id, "problems", lambda: generate_problems(insights))


def run_strategies(project_id: str, problem: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str | None]:
    return _run_node(project_id, "strategies", lambda: generate_strategies(problem))


def _run_node(project_id: str, node: str, execute: Callable[[], tuple[list[dict[str, Any]], str, str | None]]) -> tuple[list[dict[str, Any]], str, str | None]:
    repositories.create_task_log(project_id, f"graph.{node}", "started", "受控顺序节点开始执行。")
    try:
        cards, mode, message = execute()
    except Exception:
        repositories.create_task_log(project_id, f"graph.{node}", "failed", "节点执行失败。")
        raise
    repositories.create_task_log(project_id, f"graph.{node}", "completed", f"完成 {len(cards)} 张卡；mode={mode}。")
    return cards, mode, message
