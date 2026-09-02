"""Candidate strategy generation for an explicitly selected problem."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field


class ProposedStrategy(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    actions: list[str] = Field(min_length=1, max_length=5)
    preconditions: list[str] = Field(min_length=1, max_length=5)
    tradeoffs: list[str] = Field(min_length=1, max_length=5)
    validation_items: list[str] = Field(min_length=1, max_length=5)


class ProposedStrategies(BaseModel):
    strategies: list[ProposedStrategy] = Field(min_length=2, max_length=3)


def generate_strategies(problem: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str | None]:
    if os.getenv("DEEPSEEK_API_KEY"):
        try:
            return _model_generate(problem), "model", None
        except Exception:
            return _fallback(problem), "demo_fallback", "模型暂不可用，已生成固定的本地演示策略。"
    return _fallback(problem), "demo_fallback", "未配置模型 Key，已生成固定的本地演示策略。"


def _model_generate(problem: dict[str, Any]) -> list[dict[str, Any]]:
    from openai import OpenAI

    base_url, model = os.getenv("DEEPSEEK_BASE_URL"), os.getenv("DEEPSEEK_TEXT_MODEL")
    if not base_url or not model:
        raise RuntimeError("model configuration unavailable")
    schema = ProposedStrategies.model_json_schema()
    prompt = (
        "只针对如下问题给出 2-3 个可选策略；不得声明新事实。"
        "仅返回一个 JSON 对象，不要 Markdown 或额外文字。输出必须严格符合以下 JSON Schema（所有必填字段都不得省略）：\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\n问题：\n"
        + json.dumps(problem, ensure_ascii=False)
    )
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=base_url)
    last_error: Exception | None = None
    for _ in range(2):  # initial request plus one retry for request or validation failure
        try:
            response = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], temperature=0,
                response_format={"type": "json_object"},
            )
            return [item.model_dump() for item in ProposedStrategies.model_validate_json(response.choices[0].message.content or "{}").strategies]
        except Exception as exc:
            last_error = exc
    raise RuntimeError("model strategy generation failed") from last_error


def _fallback(problem: dict[str, Any]) -> list[dict[str, Any]]:
    base = problem["title"]
    return [
        {"name": f"方案 A：聚焦回应“{base}”", "actions": ["将问题拆解为一项优先空间回应。", "在概念方案中标出对应位置与使用路径。"], "preconditions": ["项目团队确认问题边界。"], "tradeoffs": ["聚焦单一目标，其他诉求需后续统筹。"], "validation_items": ["现场核验空间条件与使用时段。"]},
        {"name": f"方案 B：分阶段验证“{base}”", "actions": ["先形成低成本试行安排。", "收集反馈后再决定深化方案。"], "preconditions": ["可安排一次用户或现场核验。"], "tradeoffs": ["验证周期增加，近期决策速度较慢。"], "validation_items": ["记录试行反馈、资源投入和冲突点。"]},
        {"name": f"方案 C：协同统筹“{base}”", "actions": ["将该问题与相关专业条件建立核对清单。", "在下一轮方案评审中同步确认。"], "preconditions": ["相关责任人可参与评审。"], "tradeoffs": ["协调成本较高，需明确责任分工。"], "validation_items": ["确认责任人、时点及可用资料。"]},
    ]
