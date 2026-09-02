"""Written architectural research report generation with a deterministic fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, Field


DEFAULT_OUTLINE = [
    {"id": "background", "title": "01 项目背景", "visible": True},
    {"id": "site", "title": "02 场地认识", "visible": True},
    {"id": "constraints", "title": "03 关键条件与矛盾", "visible": True},
    {"id": "problems", "title": "04 核心问题", "visible": True},
    {"id": "strategies", "title": "05 设计策略", "visible": True},
    {"id": "research", "title": "06 待补调研与结语", "visible": True},
]

SECTION_IDS = tuple(section["id"] for section in DEFAULT_OUTLINE)


class WrittenSection(BaseModel):
    id: Literal["background", "site", "constraints", "problems", "strategies", "research"]
    title: str = Field(min_length=2, max_length=40)
    content: str = Field(min_length=40, max_length=6000)


class WrittenReport(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    sections: list[WrittenSection] = Field(min_length=6, max_length=6)
    used_insight_ids: list[str]
    used_problem_ids: list[str]
    used_strategy_ids: list[str]
    character_count: int = Field(ge=1)


def generate_written_report(
    project: dict[str, Any],
    insights: list[dict[str, Any]],
    problems: list[dict[str, Any]],
    strategies: list[dict[str, Any]],
) -> tuple[str, str, str | None]:
    """Generate a coherent written report, or an explicit evidence-safe fallback."""
    if os.getenv("DEEPSEEK_API_KEY"):
        try:
            return _model_report(project, insights, problems, strategies), "model", None
        except Exception:
            return (
                render_markdown(project, insights, problems, strategies),
                "demo_fallback",
                "汇报模型暂不可用，已生成基于确认内容的本地结构化草稿，可继续编辑。",
            )
    return (
        render_markdown(project, insights, problems, strategies),
        "demo_fallback",
        "未配置模型 Key，已生成基于确认内容的本地结构化草稿，可继续编辑。",
    )


def _model_report(
    project: dict[str, Any],
    insights: list[dict[str, Any]],
    problems: list[dict[str, Any]],
    strategies: list[dict[str, Any]],
) -> str:
    from openai import OpenAI

    base_url = os.getenv("DEEPSEEK_BASE_URL")
    model = os.getenv("DEEPSEEK_TEXT_MODEL")
    if not base_url or not model:
        raise RuntimeError("DeepSeek report configuration is incomplete")

    allowed_insight_ids = {item["id"] for item in insights}
    required_problem_ids = {item["id"] for item in problems}
    required_strategy_ids = {item["id"] for item in strategies}
    payload = {
        "project": {
            key: project.get(key)
            for key in ("name", "project_type", "location", "stage", "objective", "tags")
        },
        "confirmed_insights": [
            {
                "id": item["id"],
                "category": item["category"],
                "title": item["title"],
                "content": item["content"],
                "sources": [
                    {
                        "file_name": source.get("file_name"),
                        "locator": source.get("locator"),
                        "quote": source.get("quote"),
                    }
                    for source in item.get("sources", [])
                ],
            }
            for item in insights
        ],
        "selected_problems": [
            {
                key: item.get(key)
                for key in (
                    "id", "title", "description", "linked_insight_ids", "evidence_status",
                    "priority", "research_gap",
                )
            }
            for item in problems
        ],
        "selected_strategies": [
            {
                key: item.get(key)
                for key in (
                    "id", "problem_id", "name", "actions", "preconditions", "tradeoffs",
                    "validation_items",
                )
            }
            for item in strategies
        ],
    }
    schema = WrittenReport.model_json_schema()
    system_prompt = """
你是建筑设计前期调研报告撰稿助手。请把系统允许的项目资料组织成书面建筑调研报告正文，而不是答辩口播、卡片清单或字段复述。

写作目标：
1. 全文约 1800—2200 个中文字符，语气自然、克制、专业，适合放入建筑设计前期调研文本。
2. 形成“项目背景→场地认识→关键条件与矛盾→核心问题→设计策略→待补调研与结语”的连续论证。
3. 场地事实只完整解释一次；后文通过概括和因果关系承接，不得重复粘贴相同句子。
4. 每个核心问题都要说明其证据基础、形成原因、可能影响和仍待核实之处。
5. 每个设计策略都要明确回应对应问题，说明空间或组织动作、适用前提、取舍及验证事项。
6. 区分事实、判断和建议。对 hypothesis、information_gap、research_gap 和 validation_items 使用“可能、仍需核实、建议进一步观察”等措辞。
7. 不得补充输入中不存在的场地事实、数值、面积、规范、消防、结构、日照、人流统计、访谈或案例。
8. 不写未选择的策略，不出现数据库 ID、JSON 字段名、模型状态或 AI 置信度。
9. 避免“综上所述”“根据以上分析”等套话堆叠，不使用“显著提升、彻底解决、确保”等无证据结论。
10. 若资料不足，不得重复凑字数；应在待补调研章节如实说明资料缺口和下一步验证方法。

六个 section id 必须依次为 background、site、constraints、problems、strategies、research。每节使用连贯自然段，可包含极少量必要的小标题，但不要输出项目符号清单。used_problem_ids 和 used_strategy_ids 必须覆盖所有输入的问题和策略；used_insight_ids 只能使用输入中的确认洞察 ID。仅输出符合给定 Schema 的 JSON 对象。
""".strip()
    user_prompt = (
        "请先在内部合并含义重复的事实，建立事实—问题—策略对应关系，再生成最终报告。"
        "不要展示思考过程。\n\n输出 JSON Schema：\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\n\n允许使用的数据：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=base_url, timeout=90)
    last_error: Exception | None = None
    for _ in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
                temperature=0.3,
                max_tokens=6000,
            )
            result = WrittenReport.model_validate_json(response.choices[0].message.content or "{}")
            _validate_model_report(
                result,
                allowed_insight_ids,
                required_problem_ids,
                required_strategy_ids,
            )
            return _sections_to_markdown(result.title, result.sections)
        except Exception as exc:
            last_error = exc
    raise RuntimeError("written report generation failed") from last_error


def _validate_model_report(
    report: WrittenReport,
    allowed_insight_ids: set[str],
    required_problem_ids: set[str],
    required_strategy_ids: set[str],
) -> None:
    ids = [section.id for section in report.sections]
    if ids != list(SECTION_IDS):
        raise ValueError("report sections are missing or out of order")
    if not set(report.used_insight_ids).issubset(allowed_insight_ids):
        raise ValueError("report cited an unavailable insight")
    if set(report.used_problem_ids) != required_problem_ids:
        raise ValueError("report did not cover every selected problem")
    if set(report.used_strategy_ids) != required_strategy_ids:
        raise ValueError("report did not cover every selected strategy")
    content = "".join(section.content for section in report.sections)
    character_count = len(re.sub(r"\s+", "", content))
    if not 1400 <= character_count <= 2600:
        raise ValueError("report length is outside the accepted range")
    sentences = [
        re.sub(r"\s+", "", sentence)
        for sentence in re.split(r"[。！？!?]", content)
        if len(re.sub(r"\s+", "", sentence)) >= 18
    ]
    if len(sentences) != len(set(sentences)):
        raise ValueError("report contains repeated sentences")


def _sections_to_markdown(title: str, sections: list[WrittenSection]) -> str:
    parts = [f"# {title}"]
    for section in sections:
        parts.extend(["", f"## {section.title}", "", section.content.strip()])
    return "\n".join(parts).strip() + "\n"


def render_markdown(
    project: dict[str, Any],
    insights: list[dict[str, Any]],
    problems: list[dict[str, Any]],
    strategies: list[dict[str, Any]],
    outline: list[dict[str, Any]] | None = None,
) -> str:
    """Render an evidence-safe written fallback without inventing project facts."""
    visible = {section["id"]: section for section in (outline or DEFAULT_OUTLINE) if section.get("visible", True)}
    problem_by_id = {problem["id"]: problem for problem in problems}
    insights_by_id = {insight["id"]: insight for insight in insights}
    categories: dict[str, list[dict[str, Any]]] = {}
    for insight in insights:
        categories.setdefault(insight["category"], []).append(insight)

    sections: list[tuple[str, str]] = []
    if "background" in visible:
        sections.append((
            visible["background"]["title"],
            f"本次工作围绕{project.get('name') or '当前项目'}展开。项目类型为{project.get('project_type') or '待进一步明确'}，"
            f"位于{project.get('location') or '待补充地点信息'}，目前处于{project.get('stage') or '前期资料分析阶段'}。"
            f"本阶段的主要任务是{project.get('objective') or '整理场地条件，并为后续设计判断建立可追溯的依据'}。",
        ))
    if "site" in visible:
        site_items = categories.get("site_fact", []) + categories.get("user_need", [])
        body = "现有资料反映出以下场地认识。" + "".join(
            f"{item['title']}，具体表现为{item['content']}。" for item in site_items
        )
        if not site_items:
            body += "当前尚缺少能够单独确认的场地事实与使用诉求，需要继续补充基础资料。"
        sections.append((visible["site"]["title"], body))
    if "constraints" in visible:
        constraints = categories.get("design_constraint", [])
        body = "在现状认识基础上，设计推进还需受到已确认条件的约束。" + "".join(
            f"其中，{item['title']}要求关注{item['content']}。" for item in constraints
        )
        if not constraints:
            body += "现阶段尚未形成独立确认的设计约束，因此相关判断只能作为后续核实方向。"
        sections.append((visible["constraints"]["title"], body))
    if "problems" in visible:
        paragraphs = []
        for problem in problems:
            evidence_titles = [
                insights_by_id[item_id]["title"]
                for item_id in problem["linked_insight_ids"]
                if item_id in insights_by_id
            ]
            evidence = "、".join(evidence_titles) or "现有确认资料"
            paragraphs.append(
                f"围绕{evidence}，本次调研将“{problem['title']}”作为核心问题。"
                f"{problem['description']}。这一判断仍需结合{problem['research_gap']}继续验证。"
            )
        sections.append((visible["problems"]["title"], "\n\n".join(paragraphs)))
    if "strategies" in visible:
        paragraphs = []
        for strategy in strategies:
            problem = problem_by_id[strategy["problem_id"]]
            paragraphs.append(
                f"针对“{problem['title']}”，本次选择“{strategy['name']}”作为下一阶段的设计回应。"
                f"主要行动包括{'；'.join(strategy['actions'])}。该策略成立的前提是{'；'.join(strategy['preconditions'])}，"
                f"同时需要接受{'；'.join(strategy['tradeoffs'])}的取舍。"
            )
        sections.append((visible["strategies"]["title"], "\n\n".join(paragraphs)))
    if "research" in visible:
        gaps = [problem["research_gap"] for problem in problems]
        validations = [item for strategy in strategies for item in strategy["validation_items"]]
        body = (
            "以上结论仍处于设计前期研究阶段。后续需要重点补充"
            + "；".join(dict.fromkeys(gaps + validations))
            + "。这些核实工作将用于判断问题强度、策略适用条件及其空间影响，当前内容不构成规划、消防、结构或其他专业审查结论。"
        )
        sections.append((visible["research"]["title"], body))

    parts = [f"# {project['name']}｜前期场地调研报告"]
    for title, content in sections:
        parts.extend(["", f"## {title}", "", content])
    return "\n".join(parts).strip() + "\n"
