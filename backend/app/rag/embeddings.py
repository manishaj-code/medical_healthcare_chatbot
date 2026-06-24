"""Text embedding providers for RAG."""
from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.database import get_settings


class EmbeddingProvider(Protocol):
    @property
    def dimensions(self) -> int: ...

    async def embed_text(self, text: str, *, query: bool = False) -> list[float]: ...

    async def embed_batch(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class HashEmbeddingProvider:
    """Deterministic local embeddings for dev/tests without an API key."""

    def __init__(self, dimensions: int = 768) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed_sync(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vec: list[float] = []
        seed = int.from_bytes(digest[:8], "big")
        for i in range(self._dimensions):
            seed = (seed * 1_103_515_245 + 12_345 + i) & 0xFFFFFFFFFFFFFFFF
            vec.append((seed % 10_000) / 10_000.0 - 0.5)
        return _normalize(vec)

    async def embed_text(self, text: str, *, query: bool = False) -> list[float]:
        prefix = "query:" if query else "doc:"
        return self._embed_sync(prefix + text)

    async def embed_batch(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        return [await self.embed_text(t, query=query) for t in texts]


class GeminiEmbeddingProvider:
    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_text(self, text: str, *, query: bool = False) -> list[float]:
        results = await self.embed_batch([text], query=query)
        return results[0]

    async def embed_batch(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        import google.generativeai as genai

        genai.configure(api_key=self._api_key)
        task_type = "retrieval_query" if query else "retrieval_document"
        out: list[list[float]] = []
        batch_size = 16
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            result = genai.embed_content(
                model=self._model,
                content=batch,
                task_type=task_type,
            )
            embeddings = result.get("embedding")
            if embeddings is None:
                raise RuntimeError("Gemini embed_content returned no embedding")
            if batch and isinstance(embeddings[0], (int, float)):
                out.append([float(x) for x in embeddings])
            else:
                out.extend([[float(x) for x in row] for row in embeddings])
        return out


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.rag_embedding_provider == "gemini" and settings.gemini_api_key:
        return GeminiEmbeddingProvider(
            settings.gemini_api_key,
            settings.rag_embedding_model,
            settings.rag_embedding_dimensions,
        )
    return HashEmbeddingProvider(settings.rag_embedding_dimensions)
