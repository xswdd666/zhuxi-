"""Confirmation-gated downstream APIs: problems, strategies, and Markdown exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.agents import graph
from app.agents.reporter import DEFAULT_OUTLINE, generate_written_report
from app.db import OUTPUT_DIR
from app.schemas import MarkdownExport, Problem, ProblemUpdate, Report, ReportUpdate, Strategy, StrategyCreate, StrategyUpdate
from app.services import repositories


router = APIRouter(prefix="/api")


class StrategyGenerateRequest(BaseModel):
    problem_ids: list[str] | None = Field(default=None, max_length=20)


def _project_or_404(project_id: str) -> dict[str, Any]:
    project = repositories.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在。")
    return project


def _gate(message: str, *, code: str = "GATE_BLOCKED", details: dict[str, Any] | None = None) -> None:
    raise HTTPException(status_code=409, detail={"code": code, "message": message, "details": details or {}})


def _validated_report_inputs(project_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the formal-report allowlist without vector retrieval or model calls."""
    project = _project_or_404(project_id)
    insights = [item for item in repositories.list_insights(project_id) if item["review_status"] == "confirmed"]
    all_problems = {item["id"]: item for item in repositories.list_problems(project_id) if item["status"] == "ready"}
    selected_problem_ids = {problem_id for problem_id, problem in all_problems.items() if problem["selected"]}
    strategies = [item for item in repositories.list_strategies(project_id) if item["selected"] and item["problem_id"] in selected_problem_ids]
    if not insights:
        _gate("汇报需要至少一张已确认洞察；edited 洞察请再次确认。")
    if not selected_problem_ids:
        _gate("请先选择至少一个问题，再生成汇报。")
    if missing := [problem_id for problem_id in selected_problem_ids if not any(item["problem_id"] == problem_id for item in strategies)]:
        _gate(
            "每个已选问题都必须选择一条对应策略后才能生成报告。",
            code="STRATEGY_SELECTION_INCOMPLETE",
            details={
                "selected_problem_count": len(selected_problem_ids),
                "completed_problem_count": len(selected_problem_ids) - len(missing),
                "missing_problems": [{"id": problem_id, "title": all_problems[problem_id]["title"]} for problem_id in missing],
            },
        )
    confirmed_ids = {item["id"] for item in insights}
    problems = [all_problems[problem_id] for problem_id in selected_problem_ids]
    if any(not set(problem["linked_insight_ids"]).intersection(confirmed_ids) for problem in problems):
        _gate("已选问题缺少已确认洞察证据，无法进入正式汇报。")
    return project, insights, problems, strategies


def _export_report(report: dict[str, Any]) -> dict[str, Any]:
    project = _project_or_404(report["project_id"])
    safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in project["name"]).strip("_") or "筑析汇报"
    filename = f"{safe_name}-前期分析.md"
    export_id = repositories.new_id()
    path = OUTPUT_DIR / f"{export_id}_{filename}"
    path.write_text(report["content"], encoding="utf-8")
    record = repositories.create_export(report["project_id"], str(path), export_id=export_id)
    repositories.create_task_log(report["project_id"], "graph.reporter", "completed", f"已导出 {filename}。")
    return {key: value for key, value in {**record, "filename": filename, "content": report["content"]}.items() if key != "path"}


@router.post("/projects/{project_id}/problems:generate", response_model=dict)
def generate_problems(project_id: str) -> dict[str, Any]:
    _project_or_404(project_id)
    inputs = [item for item in repositories.list_insights(project_id) if item["review_status"] == "confirmed"]
    if not inputs:
        _gate("请先确认至少一张洞察卡，再生成问题卡。")
    proposed, mode, message = graph.run_problems(project_id, inputs)
    problems = [repositories.create_problem(project_id, **item, status="ready") for item in proposed]
    return {"problems": problems, "mode": mode, "message": message}


@router.get("/projects/{project_id}/problems", response_model=dict[str, list[Problem]])
def list_problems(project_id: str) -> dict[str, list[dict[str, Any]]]:
    _project_or_404(project_id)
    return {"problems": repositories.list_problems(project_id)}


@router.patch("/problems/{problem_id}", response_model=Problem)
def select_problem(problem_id: str, payload: ProblemUpdate) -> dict[str, Any]:
    problem = repositories.get_problem(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="问题卡不存在。")
    if payload.selected and problem["status"] != "ready":
        _gate("只有状态为 ready 的问题可以被选择。")
    updated = repositories.update_problem_selected(problem_id, payload.selected)
    assert updated is not None
    return updated


@router.get("/projects/{project_id}/strategies", response_model=dict[str, list[Strategy]])
def list_strategies(project_id: str) -> dict[str, list[dict[str, Any]]]:
    _project_or_404(project_id)
    return {"strategies": repositories.list_strategies(project_id)}


@router.post("/projects/{project_id}/strategies:generate", response_model=dict)
def generate_strategies(project_id: str, payload: StrategyGenerateRequest) -> dict[str, Any]:
    _project_or_404(project_id)
    available = {item["id"]: item for item in repositories.list_problems(project_id) if item["status"] == "ready" and item["selected"]}
    requested_ids = payload.problem_ids if payload.problem_ids is not None else list(available)
    missing = [problem_id for problem_id in requested_ids if problem_id not in available]
    if missing or not requested_ids:
        _gate("请先从当前项目选择至少一个状态为 ready 的问题，再生成策略。")
    strategies: list[dict[str, Any]] = []
    modes: set[str] = set()
    messages: list[str] = []
    outcomes: dict[str, str] = {}
    existing_by_problem: dict[str, list[dict[str, Any]]] = {}
    for strategy in repositories.list_strategies(project_id):
        existing_by_problem.setdefault(strategy["problem_id"], []).append(strategy)
    for problem_id in requested_ids:
        existing = existing_by_problem.get(problem_id, [])
        if any(item["selected"] for item in existing):
            strategies.extend(existing)
            outcomes[problem_id] = "reused"
            continue
        if existing:
            repositories.replace_unselected_generated_strategies(problem_id)
        proposed, mode, message = graph.run_strategies(project_id, available[problem_id])
        modes.add(mode)
        if message:
            messages.append(message)
        strategies.extend(repositories.create_strategy(project_id, problem_id, **item) for item in proposed)
        outcomes[problem_id] = "regenerated" if existing else "created"
    return {"strategies": strategies, "outcomes": outcomes, "mode": "model" if modes == {"model"} else "demo_fallback", "message": "；".join(dict.fromkeys(messages)) or None}


@router.post("/problems/{problem_id}/strategies", response_model=Strategy, status_code=201)
def create_custom_strategy(problem_id: str, payload: StrategyCreate) -> dict[str, Any]:
    problem = repositories.get_problem(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="问题卡不存在。")
    if problem["status"] != "ready" or not problem["selected"]:
        _gate("只能为当前已选且状态为 ready 的问题添加策略。")
    project_id = repositories.get_problem_project_id(problem_id)
    assert project_id is not None
    return repositories.create_strategy(project_id, problem_id, **payload.model_dump(), is_custom=True)


@router.patch("/strategies/{strategy_id}", response_model=Strategy)
def select_strategy(strategy_id: str, payload: StrategyUpdate) -> dict[str, Any]:
    original = repositories.get_strategy(strategy_id)
    if original is None:
        raise HTTPException(status_code=404, detail="策略卡不存在。")
    changes = payload.model_dump(exclude_unset=True)
    if "selected" in changes:
        strategy = repositories.update_strategy_selected(strategy_id, changes.pop("selected"))
        assert strategy is not None
    else:
        strategy = original
    if changes:
        strategy = repositories.update_strategy(strategy_id, **changes)
    if strategy is None:
        raise HTTPException(status_code=404, detail="策略卡不存在。")
    return strategy


@router.delete("/strategies/{strategy_id}", response_model=dict)
def delete_strategy(strategy_id: str) -> dict[str, Any]:
    if not repositories.delete_strategy(strategy_id):
        raise HTTPException(status_code=404, detail="策略卡不存在。")
    return {"deleted": True, "strategy_id": strategy_id}


@router.post("/projects/{project_id}/reports:generate", response_model=dict)
def generate_report(project_id: str) -> dict[str, Any]:
    project, insights, problems, strategies = _validated_report_inputs(project_id)
    outline = [section.copy() for section in DEFAULT_OUTLINE]
    content, mode, message = generate_written_report(project, insights, problems, strategies)
    report = repositories.create_report(project_id, outline, content)
    repositories.create_task_log(
        project_id,
        "graph.reporter",
        "completed",
        f"已生成书面建筑调研报告，使用 {len(insights)} 张确认洞察、{len(problems)} 个问题和 {len(strategies)} 条策略；mode={mode}。",
    )
    return {"report": report, "mode": mode, "message": message}


@router.get("/projects/{project_id}/report", response_model=dict[str, Report])
def get_current_report(project_id: str) -> dict[str, dict[str, Any]]:
    _project_or_404(project_id)
    report = repositories.get_latest_report(project_id)
    if report is None:
        raise HTTPException(status_code=404, detail="当前项目尚未生成汇报。")
    return {"report": report}


@router.patch("/reports/{report_id}", response_model=Report)
def update_report(report_id: str, payload: ReportUpdate) -> dict[str, Any]:
    report = repositories.update_report(report_id, **payload.model_dump(exclude_unset=True))
    if report is None:
        raise HTTPException(status_code=404, detail="汇报不存在。")
    return report


@router.post("/reports/{report_id}/export/markdown", response_model=dict[str, MarkdownExport])
def export_report_markdown(report_id: str) -> dict[str, dict[str, Any]]:
    report = repositories.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="汇报不存在。")
    return {"export": _export_report(report)}


@router.post("/projects/{project_id}/exports/markdown", response_model=dict[str, MarkdownExport])
def export_markdown(project_id: str) -> dict[str, dict[str, Any]]:
    _project_or_404(project_id)
    report = repositories.get_latest_report(project_id)
    if report is None:
        _gate("请先生成并保存汇报，再导出 Markdown。")
    return {"export": _export_report(report)}


@router.get("/exports/{export_id}/download")
def download_export(export_id: str) -> FileResponse:
    record = repositories.get_export(export_id)
    if record is None:
        raise HTTPException(status_code=404, detail="导出文件不存在。")
    path = Path(record["path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="导出文件已不可用。")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)
