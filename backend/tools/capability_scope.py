from enum import Enum
from dataclasses import dataclass
from typing import Set


class CapabilityScope(Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    ADMIN = "admin"


@dataclass
class AgentCapabilities:
    agent_type: str
    scope: CapabilityScope
    allowed_tools: Set[str]
    max_tokens: int
    max_latency_ms: int


DEFAULT_CAPABILITIES = {
    "security": AgentCapabilities(
        agent_type="security",
        scope=CapabilityScope.READ_ONLY,
        allowed_tools={"code_search", "pattern_match", "dependency_check"},
        max_tokens=4000,
        max_latency_ms=60000,
    ),
    "quality": AgentCapabilities(
        agent_type="quality",
        scope=CapabilityScope.READ_ONLY,
        allowed_tools={"code_search", "complexity_analysis", "style_check"},
        max_tokens=4000,
        max_latency_ms=60000,
    ),
    "tests": AgentCapabilities(
        agent_type="tests",
        scope=CapabilityScope.READ_ONLY,
        allowed_tools={"code_search", "test_pattern_analysis", "coverage_check"},
        max_tokens=4000,
        max_latency_ms=60000,
    ),
    "docs": AgentCapabilities(
        agent_type="docs",
        scope=CapabilityScope.READ_ONLY,
        allowed_tools={"code_search", "docstring_check", "api_doc_validation"},
        max_tokens=4000,
        max_latency_ms=60000,
    ),
}


def get_capabilities(agent_type: str) -> AgentCapabilities:
    return DEFAULT_CAPABILITIES.get(agent_type, AgentCapabilities(
        agent_type=agent_type,
        scope=CapabilityScope.READ_ONLY,
        allowed_tools=set(),
        max_tokens=4000,
        max_latency_ms=60000,
    ))