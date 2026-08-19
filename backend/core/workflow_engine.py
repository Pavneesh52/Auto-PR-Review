from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from uuid import UUID
from backend.models.enums import AgentType


class WorkflowEngine(ABC):
    @abstractmethod
    async def execute_review(self, review_id: UUID, diff: str, repo: str, pr_number: int) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def resume_review(self, review_id: UUID, checkpoint: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_state(self, review_id: UUID) -> Optional[Dict[str, Any]]:
        pass


class WorkflowEngineFactory:
    _engine: Optional[WorkflowEngine] = Noney

    @classmethod
    def set_engine(cls, engine: WorkflowEngine) -> None:
        cls._engine = engine

    @classmethod
    def get_engine(cls) -> WorkflowEngine:
        if cls._engine is None:
            raise RuntimeError("Workflow engine not initialized")
        return cls._engine