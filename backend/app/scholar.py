"""Semantic Scholar 学术检索核心逻辑（供 MCP Server / 其他模块复用）。"""

from __future__ import annotations

import re

import httpx

from app.config import settings
from app.llm import chat_completion
from app.prompts import SIMILAR_QUERY_SYSTEM

GRAPH_BASE = "https://api.semanticscholar.org/graph/v1"
REC_BASE = "https://api.semanticscholar.org/recommendations/v1"

PAPER_FIELDS = (
    "paperId,title,abstract,year,citationCount,url,externalIds,"
    "authors,venue,publicationTypes,openAccessPdf,tldr"
)


class ScholarError(Exception):
    """学术检索业务错误。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key
    return headers


def _author_names(authors: list | None) -> list[str]:
    if not authors:
        return []
    names: list[str] = []
    for a in authors:
        if isinstance(a, dict) and a.get("name"):
            names.append(str(a["name"]))
    return names


def _normalize_paper(raw: dict) -> dict:
    external = raw.get("externalIds") or {}
    oa = raw.get("openAccessPdf") or {}
    tldr = raw.get("tldr") or {}
    return {
        "paper_id": raw.get("paperId") or "",
        "title": raw.get("title") or "Untitled",
        "abstract": (raw.get("abstract") or "").strip() or None,
        "tldr": (tldr.get("text") or "").strip() or None,
        "year": raw.get("year"),
        "citation_count": raw.get("citationCount"),
        "venue": raw.get("venue") or None,
        "authors": _author_names(raw.get("authors")),
        "url": raw.get("url")
        or (
            f"https://www.semanticscholar.org/paper/{raw.get('paperId')}"
            if raw.get("paperId")
            else None
        ),
        "doi": external.get("DOI"),
        "open_access_pdf": oa.get("url") or None,
    }


async def extract_search_query(text: str) -> str:
    """从长文/中文内容提炼适合 Semantic Scholar 的英文检索式。"""
    cleaned = text.strip()
    if len(cleaned) <= 220 and re.fullmatch(
        r"[\x00-\x7F\s\-_:.,;!?()\[\]\"']+", cleaned or ""
    ):
        return cleaned

    snippet = cleaned[:4000]
    try:
        query = await chat_completion(SIMILAR_QUERY_SYSTEM, snippet)
        query = query.strip().strip('"').strip("'")
        query = re.sub(r"\s+", " ", query)
        return query[:300] if query else cleaned[:200]
    except Exception:
        return cleaned[:200]


async def search_papers(query: str, limit: int = 5) -> list[dict]:
    params = {
        "query": query,
        "limit": min(max(limit, 1), 20),
        "fields": PAPER_FIELDS,
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.get(
            f"{GRAPH_BASE}/paper/search",
            params=params,
            headers=_headers(),
        )
        if resp.status_code == 429:
            raise ScholarError(
                "学术检索请求过于频繁，请稍后重试；可在 .env 配置 SEMANTIC_SCHOLAR_API_KEY 提高限额",
                status_code=429,
            )
        if resp.status_code >= 400:
            raise ScholarError(
                f"Semantic Scholar 搜索失败: {resp.text[:300]}",
                status_code=502,
            )
        data = resp.json()

    return [_normalize_paper(p) for p in (data.get("data") or []) if p.get("paperId")]


async def recommend_similar(paper_id: str, limit: int = 10) -> list[dict]:
    params = {
        "limit": min(max(limit, 1), 20),
        "fields": PAPER_FIELDS,
        "from": "recent",
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.get(
            f"{REC_BASE}/papers/forpaper/{paper_id}",
            params=params,
            headers=_headers(),
        )
        if resp.status_code == 404:
            return []
        if resp.status_code == 429:
            raise ScholarError(
                "学术检索请求过于频繁，请稍后重试；可在 .env 配置 SEMANTIC_SCHOLAR_API_KEY 提高限额",
                status_code=429,
            )
        if resp.status_code >= 400:
            raise ScholarError(
                f"相似文献推荐失败: {resp.text[:300]}",
                status_code=502,
            )
        data = resp.json()

    return [
        _normalize_paper(p)
        for p in (data.get("recommendedPapers") or [])
        if p.get("paperId")
    ]


async def find_similar_papers(text: str, limit: int = 8) -> dict:
    """根据用户输入找种子论文，再推荐相似文献。"""
    query = await extract_search_query(text)
    if not query.strip():
        raise ScholarError("无法从输入中提取有效检索词", status_code=400)

    seeds = await search_papers(query, limit=5)
    if not seeds:
        return {
            "query": query,
            "seed": None,
            "papers": [],
            "message": "未找到匹配的种子论文，请尝试更具体的英文标题或关键词",
            "via": "mcp",
        }

    seed = seeds[0]
    similar = await recommend_similar(seed["paper_id"], limit=limit)

    if not similar:
        similar = [p for p in seeds[1:] if p["paper_id"] != seed["paper_id"]]
        if not similar:
            similar = seeds[:limit]

    papers = [p for p in similar if p["paper_id"] != seed["paper_id"]][:limit]

    return {
        "query": query,
        "seed": seed,
        "papers": papers,
        "message": None if papers else "找到了种子论文，但暂无相似推荐",
        "via": "mcp",
    }
