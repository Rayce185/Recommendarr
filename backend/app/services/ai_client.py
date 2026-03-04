"""AI client — unified interface for LLM providers.

Supports Ollama, OpenAI-compatible, OpenAI, and Anthropic.
All providers are called through a common interface returning plain text.
"""

import logging
from typing import Optional

import httpx

from app.services.ai_config import AIConfig, LLMConfig, get_ai_config

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


async def llm_complete(prompt: str, system: str = "", config: Optional[AIConfig] = None) -> Optional[str]:
    """Send a prompt to the configured LLM provider. Returns text or None on failure.

    This is the single entry point for all LLM calls in Recommendarr.
    Falls back gracefully — callers should always have a non-AI fallback.
    """
    cfg = config or get_ai_config()
    if not cfg.is_llm_enabled:
        return None

    llm = cfg.llm
    try:
        if llm.provider == "ollama":
            return await _ollama_complete(llm, prompt, system)
        elif llm.provider in ("openai_compatible", "openai"):
            return await _openai_complete(llm, prompt, system)
        elif llm.provider == "anthropic":
            return await _anthropic_complete(llm, prompt, system)
        else:
            logger.warning(f"Unknown LLM provider: {llm.provider}")
            return None
    except Exception as e:
        logger.error(f"LLM call failed ({llm.provider}): {e}")
        return None


async def _ollama_complete(llm: LLMConfig, prompt: str, system: str) -> Optional[str]:
    """Ollama /api/generate endpoint."""
    url = f"{llm.endpoint.rstrip('/')}/api/generate"
    payload = {
        "model": llm.model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": llm.temperature, "num_predict": llm.max_tokens},
    }
    if system:
        payload["system"] = system
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()


async def _openai_complete(llm: LLMConfig, prompt: str, system: str) -> Optional[str]:
    """OpenAI / OpenAI-compatible chat completions endpoint."""
    endpoint = llm.endpoint.rstrip("/") if llm.endpoint else "https://api.openai.com/v1"
    url = f"{endpoint}/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    headers = {"Content-Type": "application/json"}
    if llm.api_key:
        headers["Authorization"] = f"Bearer {llm.api_key}"

    payload = {
        "model": llm.model,
        "messages": messages,
        "temperature": llm.temperature,
        "max_tokens": llm.max_tokens,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def _anthropic_complete(llm: LLMConfig, prompt: str, system: str) -> Optional[str]:
    """Anthropic Messages API."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": llm.api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": llm.model,
        "max_tokens": llm.max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"].strip()


async def test_llm_connection(llm: LLMConfig) -> dict:
    """Test LLM provider connectivity. Returns {status, message, model_info?}."""
    try:
        if llm.provider == "ollama":
            url = f"{llm.endpoint.rstrip('/')}/api/tags"
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                found = llm.model in models or any(llm.model in m for m in models)
                return {
                    "status": "ok" if found else "warning",
                    "message": f"Connected. {len(models)} models available." + ("" if found else f" Model '{llm.model}' not found."),
                    "models": models[:20],
                }
        elif llm.provider in ("openai_compatible", "openai"):
            endpoint = llm.endpoint.rstrip("/") if llm.endpoint else "https://api.openai.com/v1"
            url = f"{endpoint}/models"
            headers = {}
            if llm.api_key:
                headers["Authorization"] = f"Bearer {llm.api_key}"
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
                found = llm.model in models
                return {
                    "status": "ok" if found else "warning",
                    "message": f"Connected. {len(models)} models." + ("" if found else f" Model '{llm.model}' not listed."),
                    "models": models[:50],
                }
        elif llm.provider == "anthropic":
            # Anthropic /v1/models API for model listing
            models = []
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                    resp = await client.get(
                        "https://api.anthropic.com/v1/models",
                        headers={
                            "x-api-key": llm.api_key,
                            "anthropic-version": "2023-06-01",
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        models = sorted(
                            [m["id"] for m in data.get("data", [])],
                            reverse=True,
                        )
            except Exception as e:
                logger.warning(f"Anthropic model list failed: {e}")

            if not models:
                # Fallback: hardcoded known models if API fails
                models = [
                    "claude-sonnet-4-5-20250929",
                    "claude-haiku-4-5-20251001",
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-haiku-20241022",
                    "claude-3-opus-20240229",
                ]

            found = llm.model in models if llm.model else False
            return {
                "status": "ok" if found else "warning",
                "message": f"Connected. {len(models)} models." + ("" if found else (" Select a model." if not llm.model else f" Model '{llm.model}' not in list.")),
                "models": models,
            }
        return {"status": "error", "message": f"Unknown provider: {llm.provider}"}
    except httpx.ConnectError:
        return {"status": "error", "message": f"Cannot connect to {llm.endpoint}"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "message": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


async def list_models(llm: LLMConfig) -> list[str]:
    """List available models from the provider. Returns [] on failure."""
    try:
        result = await test_llm_connection(llm)
        return result.get("models", [])
    except Exception:
        return []
