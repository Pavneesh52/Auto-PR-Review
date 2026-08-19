from typing import List
from backend.config import settings
from sentence_transformers import SentenceTransformer
import numpy as np


class Embedder:
    def __init__(self):
        self.model = SentenceTransformer(settings.embedding_model, device=settings.embedding_device)
        self.dimensions = settings.embedding_dimensions
        # Verify model output dimensions match expected
        test_emb = self.model.encode("test")
        actual_dim = len(test_emb)
        if actual_dim != self.dimensions:
            print(f"Warning: Model outputs {actual_dim} dims, config expects {self.dimensions}. Using {actual_dim}.")
            self.dimensions = actual_dim

    async def embed(self, text: str) -> List[float]:
        # sentence-transformers is sync, run in thread pool
        import asyncio
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(None, self.model.encode, text)
        return embedding.tolist()

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        import asyncio
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(None, self.model.encode, texts)
        return [e.tolist() for e in embeddings]

    def count_tokens(self, text: str) -> int:
        # Rough approximation: ~4 chars per token
        return len(text) // 4

    def chunk_text(self, text: str, max_tokens: int = 500, overlap: int = 50) -> List[str]:
        # Simple character-based chunking since we don't have tiktoken
        chars_per_token = 4
        max_chars = max_tokens * chars_per_token
        overlap_chars = overlap * chars_per_token
        
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
            start = end - overlap_chars
        return chunks