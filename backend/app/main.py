import json
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.documents import export_docx, export_pdf, parse_document_upload
from app.extract import extract_metadata
from app.llm import chat_completion_stream
from app.mcp_client import call_find_similar_literature, list_academic_tools
from app.prompts import POLISH_SYSTEM, SUMMARIZE_SYSTEM, TRANSLATE_SYSTEM
from app.storage import get_cover_path, get_meta, get_original_path

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="文献处理 Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "https://literatureprocessingagent-production.up.railway.app",
    ],
    allow_origin_regex=r"https://.*\.up\.railway\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待处理的文献文本")
    target_language: str | None = Field(None, description="翻译目标语言，如：中文、English")


class ProcessResponse(BaseModel):
    result: str
    task: str


class ImagePreview(BaseModel):
    label: str
    data_url: str


class ParseDocumentResponse(BaseModel):
    file_id: str
    filename: str
    file_type: str
    text: str
    cover_url: str | None = None
    cover_data_url: str | None = None
    download_url: str
    page_count: int = 0
    table_count: int = 0
    image_count: int = 0
    char_count: int = 0
    image_previews: list[ImagePreview] = Field(default_factory=list)


class ExportRequest(BaseModel):
    content: str = Field(..., min_length=1, description="要导出的摘要内容")
    format: str = Field(..., description="导出格式：docx 或 pdf")


class SimilarRequest(BaseModel):
    text: str = Field(..., min_length=1, description="论文标题、摘要或正文片段")
    limit: int = Field(8, ge=1, le=20, description="返回相似文献数量")


class PaperItem(BaseModel):
    paper_id: str
    title: str
    abstract: str | None = None
    tldr: str | None = None
    year: int | None = None
    citation_count: int | None = None
    venue: str | None = None
    authors: list[str] = Field(default_factory=list)
    url: str | None = None
    doi: str | None = None
    open_access_pdf: str | None = None


class SimilarResponse(BaseModel):
    query: str
    seed: PaperItem | None = None
    papers: list[PaperItem]
    message: str | None = None
    via: str | None = Field(None, description="调用路径，mcp 表示经 MCP 协议")


class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1, description="论文全文、摘要或章节文本")


class ExtractResponse(BaseModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    venue: str | None = None
    keywords: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    contribution: str | None = None


@app.get("/api/health")
async def health():
    mcp_tools: list[str] = []
    mcp_ok = False
    try:
        mcp_tools = await list_academic_tools()
        mcp_ok = "find_similar_literature" in mcp_tools
    except Exception:
        mcp_ok = False

    return {
        "status": "ok",
        "model": settings.deepseek_model,
        "api_configured": bool(settings.deepseek_api_key),
        "scholar_api_configured": bool(settings.semantic_scholar_api_key),
        "mcp_configured": mcp_ok,
        "mcp_tools": mcp_tools,
        "mcp_mode": "stdio" if settings.mcp_scholar_command.strip() else "memory",
    }


@app.post("/api/similar-papers", response_model=SimilarResponse)
async def similar_papers(req: SimilarRequest):
    """经 MCP Client 调用学术检索工具，查找相似文献。"""
    try:
        data = await call_find_similar_literature(req.text, limit=req.limit)
        if data.get("error"):
            raise HTTPException(
                status_code=int(data.get("status_code") or 502),
                detail=str(data["error"]),
            )
        return SimilarResponse(**data)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"学术检索错误: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MCP 调用失败: {e}")


@app.post("/api/parse-document", response_model=ParseDocumentResponse)
async def parse_document(file: UploadFile = File(...)):
    """上传 PDF / Word：提取文本/表格、生成封面、保存原件供下载。"""
    data = await parse_document_upload(file)
    return ParseDocumentResponse(**data)


@app.get("/api/uploads/{file_id}/cover")
async def upload_cover(file_id: str):
    path = get_cover_path(file_id)
    if not path:
        raise HTTPException(status_code=404, detail="封面不存在")
    return FileResponse(path, media_type="image/png", filename="cover.png")


@app.get("/api/uploads/{file_id}/download")
async def upload_download(file_id: str):
    meta = get_meta(file_id)
    path = get_original_path(file_id)
    if not meta or not path:
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    filename = meta.get("filename") or path.name
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{path.name}"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@app.post("/api/export")
async def export_result(req: ExportRequest):
    """将摘要结果导出为 Word 或 PDF。"""
    fmt = req.format.lower().strip()
    if fmt not in {"docx", "pdf"}:
        raise HTTPException(status_code=400, detail="format 仅支持 docx 或 pdf")

    try:
        if fmt == "docx":
            data = export_docx(req.content)
            media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = "文献摘要.docx"
        else:
            data = export_pdf(req.content)
            media = "application/pdf"
            filename = "文献摘要.pdf"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}") from e

    return Response(
        content=data,
        media_type=media,
        headers={
            "Content-Disposition": (
                f'attachment; filename="summary.{fmt}"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


def _sse_pack(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _llm_sse(task: str, system_prompt: str, user_content: str) -> AsyncIterator[str]:
    try:
        yield _sse_pack("start", {"task": task})
        async for delta in chat_completion_stream(system_prompt, user_content):
            yield _sse_pack("delta", {"text": delta})
        yield _sse_pack("done", {"task": task})
    except ValueError as e:
        yield _sse_pack("error", {"detail": str(e)})
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response is not None else str(e)
        yield _sse_pack("error", {"detail": f"LLM API 错误: {detail}"})
    except Exception as e:
        yield _sse_pack("error", {"detail": str(e)})


def _sse_response(generator: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/summarize")
async def summarize(req: ProcessRequest):
    """摘要提炼（SSE 流式输出）。"""
    return _sse_response(_llm_sse("summarize", SUMMARIZE_SYSTEM, req.text))


@app.post("/api/translate")
async def translate(req: ProcessRequest):
    """学术翻译（SSE 流式输出）。"""
    target = req.target_language or "中文"
    user_content = f"请将以下内容翻译为{target}：\n\n{req.text}"
    return _sse_response(_llm_sse("translate", TRANSLATE_SYSTEM, user_content))


@app.post("/api/polish")
async def polish(req: ProcessRequest):
    """润色优化（SSE 流式输出）。"""
    return _sse_response(_llm_sse("polish", POLISH_SYSTEM, req.text))


@app.post("/api/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest):
    """关键信息结构化抽取（标题/作者/年份/DOI/方法/数据集/指标等）。"""
    try:
        data = await extract_metadata(req.text)
        return ExtractResponse(**data)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM API 错误: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if STATIC_DIR.is_dir():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
