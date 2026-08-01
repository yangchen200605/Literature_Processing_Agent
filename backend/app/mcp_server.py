"""
学术检索 MCP Server（Model Context Protocol）。

暴露工具：
- search_academic_papers
- recommend_similar_papers
- find_similar_literature

运行（供 Cursor / 外部 MCP Client 使用）：
  cd backend
  python -m app.mcp_server
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.scholar import (
    ScholarError,
    find_similar_papers,
    recommend_similar,
    search_papers,
)

mcp = FastMCP(
    "literature-academic-search",
    instructions=(
        "Academic literature search tools powered by Semantic Scholar. "
        "Use find_similar_literature for end-to-end similar paper discovery."
    ),
)


@mcp.tool()
async def search_academic_papers(query: str, limit: int = 5) -> dict:
    """Search academic papers on Semantic Scholar by query string.

    Args:
        query: English keywords or paper title.
        limit: Max results (1-20).
    """
    try:
        papers = await search_papers(query, limit=limit)
        return {"query": query, "papers": papers, "count": len(papers)}
    except ScholarError as e:
        return {"error": e.message, "status_code": e.status_code}


@mcp.tool()
async def recommend_similar_papers(paper_id: str, limit: int = 8) -> dict:
    """Recommend papers similar to a known Semantic Scholar paper ID.

    Args:
        paper_id: Semantic Scholar paperId.
        limit: Max recommendations (1-20).
    """
    try:
        papers = await recommend_similar(paper_id, limit=limit)
        return {"paper_id": paper_id, "papers": papers, "count": len(papers)}
    except ScholarError as e:
        return {"error": e.message, "status_code": e.status_code}


@mcp.tool()
async def find_similar_literature(text: str, limit: int = 8) -> dict:
    """Find similar literature from a title, abstract, or paper snippet.

    Extracts a search query, finds a seed paper, then returns recommendations.

    Args:
        text: Paper title, abstract, or body snippet (Chinese or English).
        limit: Max similar papers (1-20).
    """
    try:
        return await find_similar_papers(text, limit=limit)
    except ScholarError as e:
        return {
            "query": "",
            "seed": None,
            "papers": [],
            "message": e.message,
            "error": e.message,
            "status_code": e.status_code,
            "via": "mcp",
        }


def main() -> None:
    # stdio transport：供 Cursor 等 MCP Host 连接
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
