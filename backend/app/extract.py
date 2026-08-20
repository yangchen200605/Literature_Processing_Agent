"""文献关键信息结构化抽取。"""

from __future__ import annotations

import json
import re

from fastapi import HTTPException

from app.llm import chat_completion
from app.prompts import EXTRACT_SYSTEM

EMPTY_EXTRACT = {
    "title": None,
    "authors": [],
    "year": None,
    "doi": None,
    "venue": None,
    "keywords": [],
    "methods": [],
    "datasets": [],
    "metrics": [],
    "contribution": None,
}


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _as_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [x.strip() for x in re.split(r"[,;；、|/]", value) if x.strip()]
        return items
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    return [str(value).strip()] if str(value).strip() else []


def _normalize_extract(raw: dict) -> dict:
    year = raw.get("year")
    if isinstance(year, str):
        m = re.search(r"(19|20)\d{2}", year)
        year = int(m.group(0)) if m else None
    elif isinstance(year, (int, float)):
        year = int(year)
    else:
        year = None

    doi = raw.get("doi")
    if isinstance(doi, str):
        doi = doi.strip() or None
        if doi and doi.lower() in {"null", "none", "n/a", "未提及"}:
            doi = None
    else:
        doi = None

    def _nullable_str(key: str) -> str | None:
        val = raw.get(key)
        if val is None:
            return None
        s = str(val).strip()
        if not s or s.lower() in {"null", "none", "n/a", "未提及"}:
            return None
        return s

    return {
        "title": _nullable_str("title"),
        "authors": _as_str_list(raw.get("authors")),
        "year": year,
        "doi": doi,
        "venue": _nullable_str("venue"),
        "keywords": _as_str_list(raw.get("keywords")),
        "methods": _as_str_list(raw.get("methods")),
        "datasets": _as_str_list(raw.get("datasets")),
        "metrics": _as_str_list(raw.get("metrics")),
        "contribution": _nullable_str("contribution"),
    }


async def extract_metadata(text: str) -> dict:
    snippet = text.strip()[:12000]
    if not snippet:
        raise HTTPException(status_code=400, detail="文本为空")

    try:
        raw_text = await chat_completion(EXTRACT_SYSTEM, snippet)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        data = json.loads(_strip_json_fence(raw_text))
        if not isinstance(data, dict):
            raise ValueError("模型未返回 JSON 对象")
        return _normalize_extract(data)
    except Exception as e:
        # 兜底：尽量从文本里抠出一段 JSON
        match = re.search(r"\{[\s\S]*\}", raw_text)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return _normalize_extract(data)
            except Exception:
                pass
        raise HTTPException(
            status_code=502,
            detail=f"结构化抽取结果解析失败: {e}",
        ) from e
