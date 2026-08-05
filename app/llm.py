"""Klien LLM gateway (OpenAI-compatible: adaCODE, OpenRouter, dll)."""
import json
from typing import AsyncIterator

import httpx

from app.config import get_settings

TIMEOUT = httpx.Timeout(180.0, connect=15.0)


class LLMError(Exception):
    pass


def _headers(settings: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if settings.get("api_key"):
        headers["Authorization"] = f"Bearer {settings['api_key']}"
    return headers


def _endpoint(settings: dict) -> str:
    return settings["api_base"].rstrip("/") + "/chat/completions"


async def chat(
    messages: list[dict],
    model: str | None = None,
    tools: list[dict] | None = None,
    temperature: float = 0.7,
) -> dict:
    """Panggilan non-streaming. Mengembalikan message dict dari choices[0]."""
    settings = get_settings()
    payload: dict = {
        "model": model or settings["default_model"],
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(_endpoint(settings), headers=_headers(settings), json=payload)
        if resp.status_code >= 400:
            raise LLMError(f"Gateway error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Respons gateway tidak dikenal: {json.dumps(data)[:500]}") from exc


async def chat_stream(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    """Streaming token demi token (SSE delta.content)."""
    settings = get_settings()
    payload = {
        "model": model or settings["default_model"],
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream(
            "POST", _endpoint(settings), headers=_headers(settings), json=payload
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise LLMError(f"Gateway error {resp.status_code}: {body.decode()[:500]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    return
                try:
                    delta = json.loads(chunk)["choices"][0].get("delta", {})
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                content = delta.get("content")
                if content:
                    yield content
