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
from app.memory.store import get_memory_store
from app.prompts import POLISH_SYSTEM, SUMMARIZE_SYSTEM, TRANSLATE_SYSTEM
from app.rag.agent import stream_agentic_answer
from app.rag.hitl import stream_hitl_continue, stream_hitl_start
from app.rag.ingest import index_from_file_id, index_text
from app.rag.store import delete_document, list_documents
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


class RagIndexRequest(BaseModel):
    text: str | None = Field(None, description="待索引的文献全文或摘要")
    file_id: str | None = Field(None, description="已上传文件的 file_id")
    filename: str | None = Field(None, description="展示用文件名（粘贴文本时可选）")
    doc_id: str | None = Field(None, description="自定义文档 ID，默认用 file_id 或文本哈希")


class RagIndexResponse(BaseModel):
    doc_id: str
    filename: str
    chunk_count: int
    char_count: int
    indexed_at: float


class RagDocumentItem(BaseModel):
    doc_id: str
    filename: str
    chunk_count: int
    char_count: int
    indexed_at: float


class RagAskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="针对已索引文献的提问")
    doc_ids: list[str] = Field(default_factory=list, description="限定检索的文档 ID，空则搜全部")
    top_k: int = Field(6, ge=1, le=20, description="检索片段数量")
    session_id: str | None = Field(None, description="短期记忆会话 ID（checkpoint）")
    save_to_long_term: bool = Field(True, description="是否将本轮 QA 写入长期记忆")
    human_in_the_loop: bool = Field(False, description="启用人工审核：规划与作答前暂停")


class RagContinueRequest(BaseModel):
    run_id: str = Field(..., min_length=1, description="HITL 运行 ID")
    action: str = Field("approve", description="approve | edit_queries | refine | reject")
    edited_queries: list[str] = Field(default_factory=list, description="修改后的检索查询（plan 阶段）")
    extra_queries: list[str] = Field(default_factory=list, description="补充检索查询（answer 阶段）")
    feedback: str | None = Field(None, description="用户补充说明")


class MemorySessionCreateRequest(BaseModel):
    doc_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class MemorySessionResponse(BaseModel):
    session_id: str
    doc_ids: list[str]
    created_at: float
    updated_at: float
    checkpoint_count: int
    turn_count: int


class MemoryCheckpointItem(BaseModel):
    checkpoint_id: str
    session_id: str
    phase: str
    message: str
    sequence: int
    created_at: float


class MemoryLongTermItem(BaseModel):
    memory_id: str
    kind: str
    title: str
    content: str
    doc_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None
    created_at: float
    updated_at: float


class MemoryNoteRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    doc_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None


class RagSourceItem(BaseModel):
    index: int
    doc_id: str
    filename: str
    text: str
    page: int | None = None
    char_start: int = 0
    char_end: int = 0
    score: float | None = None


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
        "rag_configured": True,
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


@app.post("/api/rag/index", response_model=RagIndexResponse)
async def rag_index(req: RagIndexRequest):
    """将文献分块并写入向量库，供问答检索。"""
    try:
        if req.file_id:
            data = index_from_file_id(req.file_id)
        elif req.text and req.text.strip():
            data = index_text(
                req.text,
                doc_id=req.doc_id,
                filename=req.filename,
            )
        else:
            raise HTTPException(status_code=400, detail="请提供 text 或 file_id")
        return RagIndexResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"索引失败: {e}")


@app.get("/api/rag/documents", response_model=list[RagDocumentItem])
async def rag_documents():
    """列出已索引文献。"""
    return [RagDocumentItem(**item) for item in list_documents()]


@app.delete("/api/rag/documents/{doc_id}")
async def rag_delete_document(doc_id: str):
    delete_document(doc_id)
    return {"ok": True, "doc_id": doc_id}


async def _emit_rag_event(event: dict) -> str | None:
    """将 RAG/HITL 内部事件转为 SSE 字符串。"""
    event_type = event.get("type")
    if event_type == "agent_step":
        return _sse_pack("agent_step", {"step": event.get("step")})
    if event_type == "human_review":
        return _sse_pack("human_review", {k: v for k, v in event.items() if k != "type"})
    if event_type == "paused":
        return _sse_pack("paused", {k: v for k, v in event.items() if k != "type"})
    if event_type == "cancelled":
        return _sse_pack("cancelled", {k: v for k, v in event.items() if k != "type"})
    if event_type == "sources":
        sources = event.get("sources") or []
        return _sse_pack(
            "sources",
            {
                "sources": [RagSourceItem(**item).model_dump() for item in sources],
                "steps": event.get("steps") or [],
                "session_id": event.get("session_id"),
            },
        )
    if event_type == "start":
        return _sse_pack("start", {"task": event.get("task", "ask")})
    if event_type == "delta":
        return _sse_pack("delta", {"text": event.get("text", "")})
    if event_type == "done":
        return _sse_pack("done", {"task": event.get("task", "ask")})
    return None


async def _rag_ask_sse(req: RagAskRequest) -> AsyncIterator[str]:
    try:
        stream = (
            stream_hitl_start(
                req.question,
                doc_ids=req.doc_ids or None,
                top_k=req.top_k,
                session_id=req.session_id,
                save_to_long_term=req.save_to_long_term,
            )
            if req.human_in_the_loop
            else stream_agentic_answer(
                req.question,
                doc_ids=req.doc_ids or None,
                top_k=req.top_k,
                session_id=req.session_id,
                save_to_long_term=req.save_to_long_term,
            )
        )
        async for event in stream:
            packed = await _emit_rag_event(event)
            if packed:
                yield packed
    except ValueError as e:
        yield _sse_pack("error", {"detail": str(e)})
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response is not None else str(e)
        yield _sse_pack("error", {"detail": f"LLM API 错误: {detail}"})
    except Exception as e:
        yield _sse_pack("error", {"detail": str(e)})


async def _rag_continue_sse(req: RagContinueRequest) -> AsyncIterator[str]:
    try:
        async for event in stream_hitl_continue(
            req.run_id,
            action=req.action,
            edited_queries=req.edited_queries or None,
            extra_queries=req.extra_queries or None,
            feedback=req.feedback,
        ):
            packed = await _emit_rag_event(event)
            if packed:
                yield packed
    except ValueError as e:
        yield _sse_pack("error", {"detail": str(e)})
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response is not None else str(e)
        yield _sse_pack("error", {"detail": f"LLM API 错误: {detail}"})
    except Exception as e:
        yield _sse_pack("error", {"detail": str(e)})


@app.post("/api/rag/ask")
async def rag_ask(req: RagAskRequest):
    """Agentic RAG 问答（可选 HITL + 记忆）。"""
    return _sse_response(_rag_ask_sse(req))


@app.post("/api/rag/ask/continue")
async def rag_ask_continue(req: RagContinueRequest):
    """HITL 继续：用户确认/修改检索计划或引用片段后继续。"""
    return _sse_response(_rag_continue_sse(req))


@app.post("/api/memory/sessions", response_model=MemorySessionResponse)
async def memory_create_session(req: MemorySessionCreateRequest):
    """创建短期记忆会话。"""
    store = get_memory_store()
    state = store.create_session(doc_ids=req.doc_ids, metadata=req.metadata)
    return MemorySessionResponse(
        session_id=state.session_id,
        doc_ids=state.doc_ids,
        created_at=state.created_at,
        updated_at=state.updated_at,
        checkpoint_count=state.checkpoint_count,
        turn_count=len(state.turns),
    )


@app.get("/api/memory/sessions/{session_id}", response_model=MemorySessionResponse)
async def memory_get_session(session_id: str):
    store = get_memory_store()
    state = store.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return MemorySessionResponse(
        session_id=state.session_id,
        doc_ids=state.doc_ids,
        created_at=state.created_at,
        updated_at=state.updated_at,
        checkpoint_count=state.checkpoint_count,
        turn_count=len(state.turns),
    )


@app.get("/api/memory/sessions/{session_id}/checkpoints", response_model=list[MemoryCheckpointItem])
async def memory_list_checkpoints(session_id: str):
    store = get_memory_store()
    if not store.get_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return [
        MemoryCheckpointItem(
            checkpoint_id=c.checkpoint_id,
            session_id=c.session_id,
            phase=c.phase,
            message=c.message,
            sequence=c.sequence,
            created_at=c.created_at,
        )
        for c in store.list_checkpoints(session_id)
    ]


@app.post("/api/memory/sessions/{session_id}/restore/{checkpoint_id}", response_model=MemorySessionResponse)
async def memory_restore_checkpoint(session_id: str, checkpoint_id: str):
    store = get_memory_store()
    state = store.restore_checkpoint(session_id, checkpoint_id)
    if not state:
        raise HTTPException(status_code=404, detail="会话或 checkpoint 不存在")
    return MemorySessionResponse(
        session_id=state.session_id,
        doc_ids=state.doc_ids,
        created_at=state.created_at,
        updated_at=state.updated_at,
        checkpoint_count=state.checkpoint_count,
        turn_count=len(state.turns),
    )


@app.get("/api/memory/long-term", response_model=list[MemoryLongTermItem])
async def memory_list_long_term(
    kind: str | None = None,
    doc_id: str | None = None,
    session_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    store = get_memory_store()
    items = store.list_long_term(
        kind=kind,
        doc_id=doc_id,
        session_id=session_id,
        limit=min(limit, 100),
        offset=offset,
    )
    return [
        MemoryLongTermItem(
            memory_id=m.memory_id,
            kind=m.kind,
            title=m.title,
            content=m.content,
            doc_ids=m.doc_ids,
            session_id=m.session_id,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in items
    ]


@app.post("/api/memory/long-term/note", response_model=MemoryLongTermItem)
async def memory_save_note(req: MemoryNoteRequest):
    store = get_memory_store()
    record = store.save_doc_note(
        title=req.title,
        content=req.content,
        doc_ids=req.doc_ids,
        session_id=req.session_id,
    )
    return MemoryLongTermItem(
        memory_id=record.memory_id,
        kind=record.kind,
        title=record.title,
        content=record.content,
        doc_ids=record.doc_ids,
        session_id=record.session_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@app.delete("/api/memory/long-term/{memory_id}")
async def memory_delete_long_term(memory_id: str):
    store = get_memory_store()
    if not store.delete_long_term(memory_id):
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"ok": True, "memory_id": memory_id}


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
