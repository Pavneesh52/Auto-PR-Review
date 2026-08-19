from typing import List, Optional
from backend.memory.tiger_client import TigerMemoryClient
from backend.memory.embedder import Embedder
from backend.config import settings
from sqlalchemy.ext.asyncio import AsyncSession


class ContextRetriever:
    def __init__(self, session: AsyncSession):
        self.tiger_client = TigerMemoryClient(session)
        self.embedder = Embedder()
        self.top_k = 10

    async def retrieve_for_diff(self, repo: str, diff: str) -> List[str]:
        diff_embedding = await self.embedder.embed(diff)
        
        chunks = await self.tiger_client.hybrid_search(
            repo=repo,
            query_embedding=diff_embedding,
            query_text=diff,
            limit=self.top_k,
        )
        
        return [chunk.content for chunk in chunks]

    async def retrieve_for_agent(
        self,
        repo: str,
        diff: str,
        agent_type: str,
        focus_keywords: Optional[List[str]] = None,
    ) -> List[str]:
        query_text = diff
        if focus_keywords:
            query_text += " " + " ".join(focus_keywords)
        
        diff_embedding = await self.embedder.embed(query_text)
        
        chunks = await self.tiger_client.hybrid_search(
            repo=repo,
            query_embedding=diff_embedding,
            query_text=query_text,
            limit=self.top_k,
        )
        
        return [chunk.content for chunk in chunks]

    async def index_repository(self, repo: str, files: dict) -> int:
        total_chunks = 0
        for file_path, content in files.items():
            chunks = self.embedder.chunk_text(content)
            chunk_data = []
            
            for i, chunk_text in enumerate(chunks):
                embedding = await self.embedder.embed(chunk_text)
                chunk_data.append({
                    "path": file_path,
                    "symbol": self._extract_symbol(chunk_text),
                    "chunk_index": i,
                    "content": chunk_text,
                    "embedding": embedding,
                    "token_count": self.embedder.count_tokens(chunk_text),
                })
            
            await self.tiger_client.upsert_chunks(repo, chunk_data)
            await self.tiger_client.upsert_file_index(
                repo, file_path, "", len(chunks)
            )
            total_chunks += len(chunks)
        
        return total_chunks

    def _extract_symbol(self, text: str) -> Optional[str]:
        lines = text.split("\n")
        for line in lines[:5]:
            stripped = line.strip()
            if stripped.startswith(("def ", "class ", "async def ")):
                return stripped.split("(")[0].split()[1]
        return None