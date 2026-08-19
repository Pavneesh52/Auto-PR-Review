from contextvars import ContextVar
from typing import Optional, Dict, Any
from uuid import UUID

workflow_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar("workflow_context", default=None)
current_review_id: ContextVar[Optional[UUID]] = ContextVar("current_review_id", default=None)
current_agent: ContextVar[Optional[str]] = ContextVar("current_agent", default=None)


def set_workflow_context(context: Dict[str, Any]):
    workflow_context.set(context)


def get_workflow_context() -> Optional[Dict[str, Any]]:
    return workflow_context.get()


def set_review_id(review_id: UUID):
    current_review_id.set(review_id)


def get_review_id() -> Optional[UUID]:
    return current_review_id.get()


def set_current_agent(agent: str):
    current_agent.set(agent)


def get_current_agent() -> Optional[str]:
    return current_agent.get()


def clear_context():
    workflow_context.set(None)
    current_review_id.set(None)
    current_agent.set(None)