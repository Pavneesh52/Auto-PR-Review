from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import asyncpg
from backend.config import settings
from backend.database.models import CodeChunk, RepoFileIndex


class TigerMemoryClient:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_chunks(self, repo: str, chunks: List[dict]) -> List[CodeChunk]:
        code_chunks = []
        for chunk in chunks:
            code_chunk = CodeChunk(
                repo=repo,
                path=chunk["path"],
                symbol=chunk.get("symbol"),
                chunk_index=chunk["chunk_index"],
                content=chunk["content"],
                embedding=chunk["embedding"],
                token_count=chunk.get("token_count"),
            )
            code_chunks.append(code_chunk)
        
        for cc in code_chunks:
            await self.session.merge(cc)
        await self.session.flush()
        return code_chunks

    async def hybrid_search(
        self,
        repo: str,
        query_embedding: List[float],
        query_text: str,
        limit: int = 10,
        vector_weight: float = 0.6,
        fts_weight: float = 0.4,
    ) -> List[CodeChunk]:
        vector_results = await self._vector_search(repo, query_embedding, limit * 2)
        fts_results = await self._fts_search(repo, query_text, limit * 2)
        
        merged = self._reciprocal_rank_fusion(
            vector_results, fts_results, vector_weight, fts_weight, limit
        )
        return merged

    async def _vector_search(
        self, repo: str, embedding: List[float], limit: int
    ) -> List[Tuple[CodeChunk, float]]:
        result = await self.session.execute(
            select(CodeChunk, CodeChunk.embedding.cosine_distance(embedding).label("distance"))
            .where(CodeChunk.repo == repo)
            .order_by("distance")
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def _fts_search(self, repo: str, query: str, limit: int) -> List[Tuple[CodeChunk, float]]:
        result = await self.session.execute(
            select(CodeChunk, func.ts_rank_cd(CodeChunk.content_tsv, func.plainto_tsquery('english', query)).label("rank"))
            .where(CodeChunk.repo == repo, CodeChunk.content_tsv.match(query))
            .order_by(text("rank DESC"))
            .limit(limit)
        )
        return [(row[0], float(row[1])) for row in result.all()]

    def _reciprocal_rank_fusion(
        self,
        vector_results: List[Tuple[CodeChunk, float]],
        fts_results: List[Tuple[CodeChunk, float]],
        vector_weight: float,
        fts_weight: float,
        limit: int,
    ) -> List[CodeChunk]:
        scores = {}
        k = 60
        
        for rank, (chunk, _) in enumerate(vector_results):
            chunk_id = str(chunk.id)
            scores[chunk_id] = scores.get(chunk_id, 0) + vector_weight / (k + rank + 1)
        
        for rank, (chunk, _) in enumerate(fts_results):
            chunk_id = str(chunk.id)
            scores[chunk_id] = scores.get(chunk_id, 0) + fts_weight / (k + rank + 1)
        
        sorted_chunks = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        
        chunk_map = {str(c.id): c for c, _ in vector_results}
        chunk_map.update({str(c.id): c for c, _ in fts_results})
        
        return [chunk_map[chunk_id] for chunk_id, _ in sorted_chunks if chunk_id in chunk_map]

    async def get_file_index(self, repo: str, path: str) -> Optional[RepoFileIndex]:
        result = await self.session.execute(
            select(RepoFileIndex).where(
                RepoFileIndex.repo == repo, RepoFileIndex.path == path
            )
        )
        return result.scalar_one_or_none()

    async def upsert_file_index(self, repo: str, path: str, sha: str, chunk_count: int) -> RepoFileIndex:
        index = RepoFileIndex(
            repo=repo,
            path=path,
            sha=sha,
            chunk_count=chunk_count,
        )
        await self.session.merge(index)
        await self.session.flush()
        return index

    async def list_repo_files(self, repo: str) -> List[RepoFileIndex]:
        result = await self.session.execute(
            select(RepoFileIndex).where(RepoFileIndex.repo == repo)
        )
        return list(result.scalars().all())