import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings


def _build_payload(system_prompt: str, user_content: str, *, stream: bool) -> dict:
    return {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "stream": stream,
    }


def _headers() -> dict[str, str]:
    if not settings.deepseek_api_key:
        raise ValueError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中设置")
    return {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }


def _chat_url() -> str:
    return f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"


async def chat_completion(system_prompt: str, user_content: str) -> str:
    """非流式：供检索词提炼等内部调用。"""
    payload = _build_payload(system_prompt, user_content, stream=False)

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(_chat_url(), headers=_headers(), json=payload)
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"]


async def chat_completion_stream(
    system_prompt: str,
    user_content: str,
) -> AsyncIterator[str]:
    """流式：逐段产出模型文本 delta。"""
    payload = _build_payload(system_prompt, user_content, stream=True)

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            _chat_url(),
            headers=_headers(),
            json=payload,
        ) as response:
            if response.status_code >= 400:
                body = await response.aread()
                raise httpx.HTTPStatusError(
                    f"LLM API 错误: {body.decode('utf-8', errors='replace')}",
                    request=response.request,
                    response=response,
                )

            async for line in response.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    if data_str == "[DONE]":
                        break
                    continue
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield content
