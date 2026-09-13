"""Embedding service for semantic code search.

Phase 10 - Generates vector embeddings for code files/chunks
and enables similarity search across the repository.
"""

from __future__ import annotations

import hashlib

import structlog
from openai import AsyncOpenAI

from pr_review_agent.config.settings import settings

logger = structlog.get_logger(__name__)

# Max chunk size for embedding (in characters)
MAX_CHUNK_SIZE = 8000


class EmbeddingService:
    """Generates and queries code embeddings using OpenAI."""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            api_key = settings.openai_api_key
            if not api_key:
                raise ValueError("OPENAI_API_KEY not configured")
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def close(self) -> None:
        if self._client:
            self._client = None

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a vector embedding for the given text."""
        try:
            response = await self.client.embeddings.create(
                model=settings.embedding_model,
                input=text[:MAX_CHUNK_SIZE],
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            return []

    async def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in a single API call."""
        if not texts:
            return []

        try:
            # Truncate each text
            truncated = [t[:MAX_CHUNK_SIZE] for t in texts]

            response = await self.client.embeddings.create(
                model=settings.embedding_model,
                input=truncated,
            )
            # Sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]
        except Exception as e:
            logger.error("batch_embedding_failed", error=str(e))
            return [[] for _ in texts]

    def chunk_code(self, content: str, file_path: str) -> list[tuple[str, int]]:
        """Split code into chunks suitable for embedding.

        Returns list of (chunk_text, chunk_index).
        """
        if len(content) <= MAX_CHUNK_SIZE:
            return [(content, 0)]

        chunks: list[tuple[str, int]] = []
        lines = content.split("\n")
        current_chunk: list[str] = []
        current_size = 0
        chunk_index = 0

        for line in lines:
            line_size = len(line) + 1  # +1 for newline
            if current_size + line_size > MAX_CHUNK_SIZE and current_chunk:
                chunks.append(("\n".join(current_chunk), chunk_index))
                chunk_index += 1
                current_chunk = []
                current_size = 0
            current_chunk.append(line)
            current_size += line_size

        if current_chunk:
            chunks.append(("\n".join(current_chunk), chunk_index))

        return chunks

    def content_hash(self, content: str) -> str:
        """Compute a content hash for caching."""
        return hashlib.sha256(content.encode()).hexdigest()

    async def find_similar_code(
        self,
        query: str,
        repo_embeddings: list[tuple[str, str, list[float]]],
        limit: int = 5,
    ) -> list[tuple[str, str, float]]:
        """Find similar code using cosine similarity.

        Args:
            query: The search query text.
            repo_embeddings: List of (file_path, content_hash, embedding).
            limit: Max results.

        Returns:
            List of (file_path, content_hash, similarity_score).
        """
        query_embedding = await self.generate_embedding(query)
        if not query_embedding:
            return []

        scored: list[tuple[str, str, float]] = []
        for file_path, content_hash, embedding in repo_embeddings:
            sim = self._cosine_similarity(query_embedding, embedding)
            scored.append((file_path, content_hash, sim))

        scored.sort(key=lambda x: x[2], reverse=True)
        return scored[:limit]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        import math

        if len(a) != len(b):
            return 0.0

        dot = sum(x * y for x, y in zip(a, b, strict=True))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)
