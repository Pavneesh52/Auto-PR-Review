from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_
from backend.database.models import (
    PRReviewRecord,
    FindingRecord,
    HITLReviewRecord,
    HITLFeedbackRecord,
    CodeChunk,
    AgentEvent,
    RepoFileIndex,
    IdempotencyKey,
)


class ReviewRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_review(self, review: PRReviewRecord) -> PRReviewRecord:
        self.session.add(review)
        await self.session.flush()
        return review

    async def get_review(self, review_id: UUID) -> Optional[PRReviewRecord]:
        result = await self.session.execute(
            select(PRReviewRecord).where(PRReviewRecord.id == review_id)
        )
        return result.scalar_one_or_none()

    async def get_review_by_repo_pr(self, repo: str, pr_number: int) -> Optional[PRReviewRecord]:
        result = await self.session.execute(
            select(PRReviewRecord).where(
                and_(PRReviewRecord.repo == repo, PRReviewRecord.pr_number == pr_number)
            )
        )
        return result.scalar_one_or_none()

    async def update_review(self, review_id: UUID, **kwargs) -> Optional[PRReviewRecord]:
        review = await self.get_review(review_id)
        if review:
            for key, value in kwargs.items():
                setattr(review, key, value)
            await self.session.flush()
        return review

    async def list_reviews(self, repo: str, limit: int = 50, offset: int = 0) -> List[PRReviewRecord]:
        result = await self.session.execute(
            select(PRReviewRecord)
            .where(PRReviewRecord.repo == repo)
            .order_by(PRReviewRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())


class FindingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_findings(self, findings: List[FindingRecord]) -> List[FindingRecord]:
        self.session.add_all(findings)
        await self.session.flush()
        return findings

    async def get_findings(self, review_id: UUID) -> List[FindingRecord]:
        result = await self.session.execute(
            select(FindingRecord).where(FindingRecord.review_id == review_id)
        )
        return list(result.scalars().all())

    async def get_findings_by_agent(self, review_id: UUID, agent_type: str) -> List[FindingRecord]:
        result = await self.session.execute(
            select(FindingRecord).where(
                and_(FindingRecord.review_id == review_id, FindingRecord.agent_type == agent_type)
            )
        )
        return list(result.scalars().all())


class HITLRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_hitl_review(self, hitl: HITLReviewRecord) -> HITLReviewRecord:
        self.session.add(hitl)
        await self.session.flush()
        return hitl

    async def get_hitl_review(self, review_id: UUID) -> Optional[HITLReviewRecord]:
        result = await self.session.execute(
            select(HITLReviewRecord).where(HITLReviewRecord.review_id == review_id)
        )
        return result.scalar_one_or_none()

    async def update_hitl_review(self, review_id: UUID, **kwargs) -> Optional[HITLReviewRecord]:
        hitl = await self.get_hitl_review(review_id)
        if hitl:
            for key, value in kwargs.items():
                setattr(hitl, key, value)
            await self.session.flush()
        return hitl

    async def create_feedback(self, feedback: HITLFeedbackRecord) -> HITLFeedbackRecord:
        self.session.add(feedback)
        await self.session.flush()
        return feedback

    async def get_feedback(self, review_id: UUID) -> List[HITLFeedbackRecord]:
        result = await self.session.execute(
            select(HITLFeedbackRecord).where(HITLFeedbackRecord.review_id == review_id)
        )
        return list(result.scalars().all())


class CodeChunkRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_chunks(self, chunks: List[CodeChunk]) -> List[CodeChunk]:
        for chunk in chunks:
            await self.session.merge(chunk)
        await self.session.flush()
        return chunks

    async def search_vector(self, repo: str, embedding: list, limit: int = 10) -> List[CodeChunk]:
        result = await self.session.execute(
            select(CodeChunk)
            .where(CodeChunk.repo == repo)
            .order_by(CodeChunk.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search_fts(self, repo: str, query: str, limit: int = 10) -> List[CodeChunk]:
        result = await self.session.execute(
            select(CodeChunk)
            .where(and_(CodeChunk.repo == repo, CodeChunk.content_tsv.match(query)))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_chunks_by_repo(self, repo: str) -> List[CodeChunk]:
        result = await self.session.execute(
            select(CodeChunk).where(CodeChunk.repo == repo)
        )
        return list(result.scalars().all())


class AgentEventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_event(self, event: AgentEvent) -> AgentEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def create_events_batch(self, events: List[AgentEvent]) -> List[AgentEvent]:
        self.session.add_all(events)
        await self.session.flush()
        return events

    async def get_events(self, review_id: UUID) -> List[AgentEvent]:
        result = await self.session.execute(
            select(AgentEvent)
            .where(AgentEvent.review_id == review_id)
            .order_by(AgentEvent.ts)
        )
        return list(result.scalars().all())


class RepoFileIndexRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_file_index(self, index: RepoFileIndex) -> RepoFileIndex:
        await self.session.merge(index)
        await self.session.flush()
        return index

    async def get_file_index(self, repo: str, path: str) -> Optional[RepoFileIndex]:
        result = await self.session.execute(
            select(RepoFileIndex).where(
                and_(RepoFileIndex.repo == repo, RepoFileIndex.path == path)
            )
        )
        return result.scalar_one_or_none()

    async def list_repo_files(self, repo: str) -> List[RepoFileIndex]:
        result = await self.session.execute(
            select(RepoFileIndex).where(RepoFileIndex.repo == repo)
        )
        return list(result.scalars().all())


class IdempotencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_and_set(self, key: str) -> bool:
        existing = await self.session.get(IdempotencyKey, key)
        if existing:
            return False
        self.session.add(IdempotencyKey(key=key))
        await self.session.flush()
        return True