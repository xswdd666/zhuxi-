"""Insight extraction with validated model output and deterministic offline fallback."""

from __future__ import annotations

import json
import os
import re
from base64 import b64encode
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProposedInsight(BaseModel):
    category: Literal["site_fact", "design_constraint", "user_need", "information_gap"]
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=1000)
    source_chunk_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    observation: str | None = Field(default=None, max_length=1000)


class ProposedInsights(BaseModel):
    insights: list[ProposedInsight] = Field(min_length=1, max_length=12)


KEYWORDS = {
    "design_constraint": ("约束", "不得", "不超过", "保留", "限制", "高度", "必须"),
    "user_need": ("诉求", "需要", "希望", "使用者", "儿童", "老年", "活动空间"),
    "information_gap": ("缺口", "未提供", "未知", "待核实", "待确认", "缺少"),
}


def extract_insights(chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, str | None]:
    """Use DeepSeek when configured; otherwise create source-bound, reviewable cards."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    text_chunks = [chunk for chunk in chunks if chunk["source_type"] == "text"]
    image_chunks = [chunk for chunk in chunks if chunk["source_type"] == "image"]
    if api_key:
        insights: list[dict[str, Any]] = []
        used_model = False
        fallback_chunks: list[dict[str, Any]] = []
        if text_chunks:
            try:
                insights.extend(_model_extract(api_key, text_chunks))
                used_model = True
            except Exception:
                fallback_chunks.extend(text_chunks)
        for image in image_chunks:
            try:
                insights.extend(_vision_extract(api_key, image))
                used_model = True
            except Exception:
                # A visual outage must not prevent text cards or the image fallback card.
                fallback_chunks.append(image)
        insights.extend(_fallback(fallback_chunks))
        if insights:
            message = None if not fallback_chunks else "部分模型调用不可用，相关资料已生成待人工核实卡。"
            return insights, "model" if used_model else "demo_fallback", message
    if chunks:
        return _fallback(chunks), "demo_fallback", "未配置模型 Key，已使用可追溯的本地演示提取。"
    return [], "unavailable", "没有可解析的上传资料，无法生成带来源洞察。"


def _model_extract(api_key: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from openai import OpenAI

    base_url = os.getenv("DEEPSEEK_BASE_URL")
    text_model = os.getenv("DEEPSEEK_TEXT_MODEL")
    if not base_url or not text_model:
        raise RuntimeError("DeepSeek text model configuration is incomplete")

    compact_sources = [
        {"id": c["id"], "locator": c["locator"], "content": c["content"][:1200]}
        for c in chunks[:12]
    ]
    prompt = (
        "根据以下建筑项目来源片段提取洞察。只能引用给定 source_chunk_id；"
        "分类仅 site_fact/design_constraint/user_need/information_gap。"
        "所有内容是待人工审核，不得自动确认。仅输出 JSON："
        '{"insights":[{"category":"...","title":"...","content":"...","source_chunk_id":"...","confidence":0.0}]}。\n'
        + json.dumps(compact_sources, ensure_ascii=False)
    )
    client = OpenAI(api_key=api_key, base_url=base_url)
    last_error: Exception | None = None
    for _ in range(2):  # initial try plus exactly one retry
        try:
            response = client.chat.completions.create(
                model=text_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
            )
            raw = response.choices[0].message.content or "{}"
            data = ProposedInsights.model_validate_json(raw)
            permitted = {chunk["id"] for chunk in chunks}
            return [{**item.model_dump(), "_model": text_model} for item in data.insights if item.source_chunk_id in permitted]
        except Exception as exc:
            last_error = exc
    raise RuntimeError("model extraction failed") from last_error


def _vision_extract(api_key: str, chunk: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze exactly one saved image using the configured OpenAI-compatible vision model."""
    from openai import OpenAI

    base_url = os.getenv("DEEPSEEK_BASE_URL")
    vision_model = os.getenv("DEEPSEEK_VISION_MODEL")
    if not base_url or not vision_model:
        raise RuntimeError("DeepSeek vision model configuration is incomplete")
    image_path = Path(chunk["path"])
    encoded_image = b64encode(image_path.read_bytes()).decode("ascii")
    mime_type = "image/png" if chunk["file_type"].lower() == "png" else "image/jpeg"
    prompt = (
        "仅根据这张图片生成待人工审核的建筑场地观察。只允许描述肉眼可见内容、"
        "图中文字和待核实项。不得推断准确面积、限高、日照、消防、结构或法规结论。"
        "所有输出均为 pending 观察，不是确认事实。只输出 JSON："
        '{"insights":[{"category":"site_fact|information_gap","title":"...","content":"...",'
        f'"source_chunk_id":"{chunk["id"]}","confidence":0.0,"observation":"..."}}]}}'
    )
    client = OpenAI(api_key=api_key, base_url=base_url)
    last_error: Exception | None = None
    for _ in range(2):
        try:
            response = client.chat.completions.create(
                model=vision_model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded_image}"}},
                ]}],
                response_format={"type": "json_object"},
                temperature=0,
            )
            raw = response.choices[0].message.content or "{}"
            data = ProposedInsights.model_validate_json(raw)
            return [
                {**item.model_dump(), "source_chunk_id": chunk["id"], "_model": vision_model}
                for item in data.insights
                if item.category in {"site_fact", "information_gap"} and not _has_prohibited_inference(item.content)
            ]
        except Exception as exc:
            last_error = exc
    raise RuntimeError("vision extraction failed") from last_error


def _has_prohibited_inference(content: str) -> bool:
    return any(term in content for term in ("准确面积", "限高", "日照", "消防", "结构结论", "法规结论"))


def _fallback(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for chunk in chunks:
        if chunk["source_type"] == "image":
            observation = "该图片已保存；视觉模型不可用，图片中的场地信息需人工核实后再作为依据。"
            cards.append({"category": "information_gap", "title": "图片内容待人工观察", "content": observation, "source_chunk_id": chunk["id"], "confidence": 0.2, "observation": observation})
            continue
        for line in _lines(chunk["content"]):
            category = _category(line)
            if category:
                cards.append({"category": category, "title": _title(category, line), "content": line, "source_chunk_id": chunk["id"], "confidence": 0.65})
            if len(cards) >= 12:
                return cards
    if not cards:
        for chunk in chunks:
            if chunk["source_type"] == "text":
                quote = _lines(chunk["content"])[0] if _lines(chunk["content"]) else chunk["content"][:240]
                cards.append({"category": "information_gap", "title": "资料需进一步核实", "content": f"已上传文本包含以下待核实信息：{quote}", "source_chunk_id": chunk["id"], "confidence": 0.4})
                break
    return cards


def _lines(content: str) -> list[str]:
    return [line.strip(" -•\t") for line in re.split(r"[\r\n。；;]", content) if len(line.strip()) >= 4]


def _category(line: str) -> str | None:
    for category, words in KEYWORDS.items():
        if any(word in line for word in words):
            return category
    return "site_fact" if any(word in line for word in ("场地", "入口", "位于", "项目", "临")) else None


def _title(category: str, line: str) -> str:
    labels = {"site_fact": "场地事实", "design_constraint": "设计约束", "user_need": "使用诉求", "information_gap": "信息缺口"}
    return f"{labels[category]}：{line[:48]}"
