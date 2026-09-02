"""Problem-card generation from human-reviewed insights only."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProposedProblem(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    linked_insight_ids: list[str] = Field(min_length=1, max_length=6)
    evidence_status: Literal["confirmed", "hypothesis"]
    priority: Literal["low", "medium", "high"]
    research_gap: str = Field(min_length=1, max_length=500)


class ProposedProblems(BaseModel):
    problems: list[ProposedProblem] = Field(min_length=1, max_length=6)


def generate_problems(insights: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, str | None]:
    """Generate problems from confirmed insights only."""
    if os.getenv("DEEPSEEK_API_KEY"):
        try:
            return _model_generate(insights), "model", None
        except Exception:
            return _fallback(insights), "demo_fallback", "模型暂不可用，已生成明确标注的本地演示问题卡。"
    return _fallback(insights), "demo_fallback", "未配置模型 Key，已生成明确标注的本地演示问题卡。"


def _model_generate(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from openai import OpenAI

    base_url, model = os.getenv("DEEPSEEK_BASE_URL"), os.getenv("DEEPSEEK_TEXT_MODEL")
    if not base_url or not model:
        raise RuntimeError("model configuration unavailable")
    source = [{"id": i["id"], "title": i["title"], "content": i["content"], "review_status": i["review_status"]} for i in insights]
    schema = ProposedProblems.model_json_schema()
    prompt = (
        "只根据以下已人工审核洞察生成问题卡。每项必须链接给定 ID。"
        "证据不足时 evidence_status 必须为 hypothesis，并把待核实内容写入 research_gap；不得新增事实。\n"
        "仅返回一个 JSON 对象，不要 Markdown 或额外文字。输出必须严格符合以下 JSON Schema（所有必填字段都不得省略）：\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\n已审核洞察：\n"
        + json.dumps(source, ensure_ascii=False)
    )
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=base_url)
    last_error: Exception | None = None
    for _ in range(2):  # initial request plus one retry for request or validation failure
        try:
            response = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], temperature=0,
                response_format={"type": "json_object"},
            )
            data = ProposedProblems.model_validate_json(response.choices[0].message.content or "{}")
            permitted = {item["id"] for item in insights}
            result = [item.model_dump() for item in data.problems if set(item.linked_insight_ids).issubset(permitted)]
            if not result:
                raise RuntimeError("model returned no valid problem")
            return result
        except Exception as exc:
            last_error = exc
    raise RuntimeError("model problem generation failed") from last_error


def _fallback(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for insight in insights[:3]:
        title = insight["title"]
        is_gap = insight["category"] == "information_gap"
        result.append({
            "title": f"需回应：{title}",
            "description": f"围绕已审核洞察“{title}”梳理可执行的空间与调研回应。",
            "linked_insight_ids": [insight["id"]],
            "evidence_status": "hypothesis" if is_gap else "confirmed",
            "priority": "high" if insight["category"] in {"design_constraint", "user_need"} else "medium",
            "research_gap": "该问题为本地降级规则输出；实施前需由项目团队核验适用条件。" if is_gap else "仍需在方案深化前核验现场条件与使用安排。",
        })
    return result
