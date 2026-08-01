"""
MCP Client 桥接：FastAPI 通过 MCP 协议调用学术检索工具。

默认使用内存传输连接本项目的 FastMCP Server（真正走 list_tools / call_tool）。
也可配置 MCP_SCHOLAR_COMMAND 以 stdio 连接外部 MCP Server。
"""

from __future__ import annotations

import json
import logging
import shutil
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from app.config import settings

logger = logging.getLogger(__name__)


def _parse_tool_result(result) -> dict[str, Any]:
    if getattr(result, "isError", False):
        texts = [
            c.text for c in (result.content or []) if isinstance(c, TextContent)
        ]
        raise RuntimeError(texts[0] if texts else "MCP tool 调用失败")

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    for item in result.content or []:
        if isinstance(item, TextContent) and item.text:
            try:
                data = json.loads(item.text)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                return {"raw": item.text}

    return {}


@asynccontextmanager
async def _open_session() -> AsyncIterator[ClientSession]:
    """打开 MCP ClientSession：优先外部 stdio，否则内存连接本地 FastMCP。"""
    command = (settings.mcp_scholar_command or "").strip()
    if command:
        # 例: python -m app.mcp_server
        parts = command.split()
        exe = parts[0]
        args = parts[1:]
        if exe in {"python", "python3"} and not shutil.which(exe):
            exe = shutil.which("py") or exe
        params = StdioServerParameters(command=exe, args=args)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
        return

    # 内存传输：同一进程内 MCP Server ↔ Client（仍走 MCP 协议）
    from app.mcp_server import mcp as scholar_mcp

    async with create_connected_server_and_client_session(scholar_mcp) as session:
        yield session


async def list_academic_tools() -> list[str]:
    async with _open_session() as session:
        tools = await session.list_tools()
        return [t.name for t in tools.tools]


async def call_find_similar_literature(text: str, limit: int = 8) -> dict[str, Any]:
    """通过 MCP tool `find_similar_literature` 查找相似文献。"""
    async with _open_session() as session:
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        if "find_similar_literature" not in names:
            raise RuntimeError(
                f"MCP Server 未提供 find_similar_literature，当前工具: {sorted(names)}"
            )

        result = await session.call_tool(
            "find_similar_literature",
            {"text": text, "limit": limit},
        )
        data = _parse_tool_result(result)
        data.setdefault("via", "mcp")
        return data
