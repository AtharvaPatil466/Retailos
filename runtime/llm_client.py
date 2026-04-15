"""Unified LLM client — switch between Gemini and Ollama via environment variables.

Usage:
    from runtime.llm_client import get_llm_client

    client = get_llm_client()
    response = await client.generate(prompt)              # async text
    response = await client.generate(prompt, timeout=30)  # with timeout
    response = client.generate_sync(prompt)               # sync text (shelf audit etc.)

    # Multimodal (images) — only supported by Gemini
    response = client.generate_sync(prompt, image_base64=img, mime_type="image/jpeg")

Configuration (env vars):
    LLM_PROVIDER=gemini   (default) — uses Google Gemini API
    LLM_PROVIDER=ollama   — uses local Ollama server

    # Gemini settings
    GEMINI_API_KEY=...
    GEMINI_MODEL=gemini-2.0-flash  (default)

    # Ollama settings
    OLLAMA_BASE_URL=http://localhost:11434  (default)
    OLLAMA_MODEL=llama3  (default)
"""

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, *, timeout: float = 30) -> str:
        """Generate text asynchronously."""

    @abstractmethod
    def generate_sync(self, prompt: str, *, image_base64: str | None = None, mime_type: str = "image/jpeg") -> str:
        """Generate text synchronously (for non-async contexts)."""

    @abstractmethod
    def get_raw_client(self):
        """Return the underlying client for advanced usage (backward compat)."""


class GeminiClient(LLMClient):
    """Google Gemini via google-genai SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        from google import genai
        self.model = model
        self.client = genai.Client(api_key=api_key) if api_key else None
        self._api_key = api_key

    async def generate(self, prompt: str, *, timeout: float = 30) -> str:
        if not self.client:
            raise RuntimeError("Gemini API key not configured")
        response = await asyncio.wait_for(
            self.client.aio.models.generate_content(
                model=self.model, contents=prompt,
            ),
            timeout=timeout,
        )
        return response.text.strip() if response.text else ""

    def generate_sync(self, prompt: str, *, image_base64: str | None = None, mime_type: str = "image/jpeg") -> str:
        if not self.client:
            raise RuntimeError("Gemini API key not configured")
        if image_base64:
            contents = [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": image_base64}},
            ]
        else:
            contents = prompt
        response = self.client.models.generate_content(
            model=self.model, contents=contents,
        )
        return response.text.strip() if response.text else ""

    def get_raw_client(self):
        return self.client


class OllamaClient(LLMClient):
    """Local Ollama server via HTTP API."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, prompt: str, *, timeout: float = 60) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()

    def generate_sync(self, prompt: str, *, image_base64: str | None = None, mime_type: str = "image/jpeg") -> str:
        payload: dict = {"model": self.model, "prompt": prompt, "stream": False}
        if image_base64:
            payload["images"] = [image_base64]
        with httpx.Client(timeout=60) as client:
            response = client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json().get("response", "").strip()

    def get_raw_client(self):
        return None


# ── Singleton ──

_instance: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return the configured LLM client (created once, reused)."""
    global _instance
    if _instance is not None:
        return _instance

    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()

    if provider == "ollama":
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.environ.get("OLLAMA_MODEL", "llama3")
        logger.info("LLM provider: Ollama (%s, model=%s)", base_url, model)
        _instance = OllamaClient(base_url=base_url, model=model)
    else:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        logger.info("LLM provider: Gemini (model=%s)", model)
        _instance = GeminiClient(api_key=api_key, model=model)

    return _instance


def reset_client():
    """Reset the singleton (useful for tests)."""
    global _instance
    _instance = None
