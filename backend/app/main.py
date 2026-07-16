from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.documents import export_docx, export_pdf, extract_text_from_upload
from app.llm import chat_completion
from app.prompts import POLISH_SYSTEM, SUMMARIZE_SYSTEM, TRANSLATE_SYSTEM

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


class ParseDocumentResponse(BaseModel):
    text: str
    filename: str


class ExportRequest(BaseModel):
    content: str = Field(..., min_length=1, description="要导出的摘要内容")
    format: str = Field(..., description="导出格式：docx 或 pdf")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": settings.deepseek_model,
        "api_configured": bool(settings.deepseek_api_key),
    }


@app.post("/api/parse-document", response_model=ParseDocumentResponse)
async def parse_document(file: UploadFile = File(...)):
    """上传 PDF / Word，提取文本供摘要使用。"""
    text, filename = await extract_text_from_upload(file)
    return ParseDocumentResponse(text=text, filename=filename)


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


@app.post("/api/summarize", response_model=ProcessResponse)
async def summarize(req: ProcessRequest):
    try:
        result = await chat_completion(SUMMARIZE_SYSTEM, req.text)
        return ProcessResponse(result=result, task="summarize")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM API 错误: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/translate", response_model=ProcessResponse)
async def translate(req: ProcessRequest):
    target = req.target_language or "中文"
    user_content = f"请将以下内容翻译为{target}：\n\n{req.text}"
    try:
        result = await chat_completion(TRANSLATE_SYSTEM, user_content)
        return ProcessResponse(result=result, task="translate")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM API 错误: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/polish", response_model=ProcessResponse)
async def polish(req: ProcessRequest):
    try:
        result = await chat_completion(POLISH_SYSTEM, req.text)
        return ProcessResponse(result=result, task="polish")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
