"""把文献文本切成带 overlap 的块，供 embedding / 检索使用。"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass

PAGE_MARKER = re.compile(r"^##\s*第\s*(\d+)\s*页", re.MULTILINE)


@dataclass
class TextChunk:
    chunk_id: str
    text: str
    index: int
    char_start: int
    char_end: int
    page: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _guess_page(char_pos: int, full_text: str) -> int | None:
    """根据 PDF 解析插入的 `## 第 N 页` 标记推断页码。"""
    prefix = full_text[:char_pos]
    matches = list(PAGE_MARKER.finditer(prefix))
    if not matches:
        return None
    return int(matches[-1].group(1))


def _find_break(text: str, min_pos: int) -> int | None:
    for marker in ("\n\n", "。", ". ", "！", "？", "\n"):
        pos = text.rfind(marker)
        if pos >= min_pos:
            return pos + (len(marker) if marker.strip() else 1)
    return None


def chunk_text(
    text: str,
    *,
    chunk_size: int = 800,
    overlap: int = 120,
    file_id: str = "doc",
) -> list[TextChunk]:
    """
    固定窗口分块。
    - chunk_size: 每块大约多少字符（中文约 400–800 较合适）
    - overlap: 相邻块重叠，避免句子被切断丢语义
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap 必须小于 chunk_size")

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]
    joined = "\n\n".join(paragraphs)

    chunks: list[TextChunk] = []
    start = 0
    idx = 0
    total = len(joined)

    while start < total:
        end = min(start + chunk_size, total)
        if end < total:
            slice_text = joined[start:end]
            break_at = _find_break(slice_text, chunk_size // 2)
            if break_at is not None:
                end = start + break_at

        piece = joined[start:end].strip()
        if piece:
            chunks.append(
                TextChunk(
                    chunk_id=f"{file_id}_{idx}_{uuid.uuid4().hex[:8]}",
                    text=piece,
                    index=idx,
                    char_start=start,
                    char_end=end,
                    page=_guess_page(start, joined),
                )
            )
            idx += 1

        if end >= total:
            break
        start = max(end - overlap, start + 1)

    return chunks
