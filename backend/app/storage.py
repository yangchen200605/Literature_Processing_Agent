"""上传文件临时存储：原件下载、封面预览。"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "uploads"
TTL_SECONDS = 24 * 60 * 60  # 24h


def _ensure_root() -> None:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


def cleanup_expired() -> None:
    _ensure_root()
    now = time.time()
    for path in UPLOAD_ROOT.iterdir():
        if not path.is_dir():
            continue
        meta = path / "meta.json"
        try:
            if meta.is_file():
                created = json.loads(meta.read_text(encoding="utf-8")).get("created_at", 0)
            else:
                created = path.stat().st_mtime
            if now - float(created) > TTL_SECONDS:
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            continue


def save_upload(
    *,
    filename: str,
    file_bytes: bytes,
    cover_png: bytes | None,
    text: str,
    meta_extra: dict | None = None,
) -> str:
    """保存原件与封面，返回 file_id。"""
    cleanup_expired()
    _ensure_root()
    file_id = uuid.uuid4().hex
    folder = UPLOAD_ROOT / file_id
    folder.mkdir(parents=True, exist_ok=False)

    suffix = Path(filename).suffix.lower() or ".bin"
    original_path = folder / f"original{suffix}"
    original_path.write_bytes(file_bytes)

    if cover_png:
        (folder / "cover.png").write_bytes(cover_png)

    meta = {
        "file_id": file_id,
        "filename": filename,
        "suffix": suffix,
        "created_at": time.time(),
        "size": len(file_bytes),
        "has_cover": bool(cover_png),
        "char_count": len(text),
        **(meta_extra or {}),
    }
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (folder / "text.txt").write_text(text, encoding="utf-8")
    return file_id


def get_meta(file_id: str) -> dict | None:
    meta_path = UPLOAD_ROOT / file_id / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_original_path(file_id: str) -> Path | None:
    folder = UPLOAD_ROOT / file_id
    if not folder.is_dir():
        return None
    for path in folder.glob("original.*"):
        return path
    return None


def get_cover_path(file_id: str) -> Path | None:
    path = UPLOAD_ROOT / file_id / "cover.png"
    return path if path.is_file() else None


def get_text(file_id: str) -> str | None:
    path = UPLOAD_ROOT / file_id / "text.txt"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None
