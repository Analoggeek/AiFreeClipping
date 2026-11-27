"""Local LLM via Ollama with schema-constrained structured output."""
from __future__ import annotations

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..config import DEFAULT_MODEL, env, ollama_host

T = TypeVar("T", bound=BaseModel)


def selected_model(explicit: str | None = None) -> str:
    """Read the selected Ollama model from persistent settings after restart."""
    if explicit:
        return explicit
    from ..db import db

    # The editable Settings value is authoritative over the process environment,
    # which may still contain a model activated earlier in this same session.
    return (
        db.get_setting("ollama_model", "")
        or db.get_setting("active_llm", "")
        or env("OLLAMA_MODEL")
        or db.get_setting("OLLAMA_MODEL", "")
        or DEFAULT_MODEL
    )


async def reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(f"{ollama_host()}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


async def tags() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{ollama_host()}/api/tags")
            return response.json().get("models", []) if response.status_code == 200 else []
    except Exception:
        return []


async def structured(
    prompt: str,
    schema: type[T],
    system: str = "You are a precise assistant. Return only valid JSON.",
    model: str | None = None,
    temperature: float = 0.1,
    timeout: float = 120,
) -> T | None:
    """Ask a local Ollama model for output matching a Pydantic schema.

    Returns None (never raises) so the deterministic heuristics can take over.
    """
    payload = {
        "model": selected_model(model),
        "stream": False,
        "format": schema.model_json_schema(),
        "options": {"temperature": temperature},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{ollama_host()}/api/chat", json=payload)
            response.raise_for_status()
            content = response.json()["message"]["content"]
        return schema.model_validate_json(_strip_fences(content))
    except (ValidationError, KeyError, json.JSONDecodeError, httpx.HTTPError, Exception):
        return None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return text.strip()
