from typing: List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class ThreatCategory(Enum):
    INJECTION = "injection"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_EXPOSURE = "data_exposure"
    DENIAL_OF_SERVICE = "denial_of_service"


class ThreatLevel(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Threat:
    id: str
    category: ThreatCategory
    level: ThreatLevel
    description: str
    mitigation: str
    component: str


THREAT_MODEL = [
    Threat(
        id="TM-001",
        category=ThreatCategory.INJECTION,
        level=ThreatLevel.CRITICAL,
        description="Prompt injection via malicious PR content",
        mitigation="Input sanitization, prompt templates with strict boundaries, output validation",
        component="LLM prompts",
    ),
    Threat(
        id="TM-002",
        category=ThreatCategory.INJECTION,
        level=ThreatLevel.HIGH,
        description="SQL injection via webhook payload",
        mitigation="Parameterized queries, ORM usage, input validation",
        component="Webhook handler",
    ),
    Threat(
        id="TM-003",
        category=ThreatCategory.AUTHENTICATION,
        level=ThreatLevel.CRITICAL,
        description="GitHub webhook signature forgery",
        mitigation="HMAC-SHA256 verification with shared secret",
        component="Webhook ingress",
    ),
    Threat(
        id="TM-004",
        category=ThreatCategory.AUTHORIZATION,
        level=ThreatLevel.HIGH,
        description="Unauthorized access to review data",
        mitigation="RBAC on API endpoints, installation-scoped GitHub tokens",
        component="API layer",
    ),
    Threat(
        id="TM-005",
        category=ThreatCategory.DATA_EXPOSURE,
        level=ThreatLevel.HIGH,
        description="Secrets leakage in logs or events",
        mitigation="Secret masking in logs, structured logging with PII detection",
        component="Observability",
    ),
    Threat(
        id="TM-006",
        category=ThreatCategory.DENIAL_OF_SERVICE,
        level=ThreatLevel.MEDIUM,
        description="LLM API exhaustion via malicious PRs",
        mitigation="Budget guards, rate limiting, circuit breakers",
        component="Economics/Orchestration",
    ),
    Threat(
        id="TM-007",
        category=ThreatCategory.INJECTION,
        level=ThreatLevel.MEDIUM,
        description="Code execution via sandbox escape",
        mitigation="Docker isolation, network disable, resource limits",
        component="Tool sandbox",
    ),
    Threat(
        id="TM-008",
        category=ThreatCategory.DATA_EXPOSURE,
        level=ThreatLevel.MEDIUM,
        description="Repository code exposure in vector store",
        mitigation="Access controls on Tiger Cloud, encryption at rest",
        component="Memory layer",
    ),
]


def get_threat_model() -> List[Threat]:
    return THREAT_MODEL


def get_threats_by_component(component: str) -> List[Threat]:
    return [t for t in THREAT_MODEL if t.component == component]