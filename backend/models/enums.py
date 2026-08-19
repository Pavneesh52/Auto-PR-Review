from enum import Enum


class AgentType(str, Enum):
    SECURITY = "security"
    QUALITY = "quality"
    TESTS = "tests"
    DOCS = "docs"
    AGGREGATOR = "aggregator"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class FindingCategory(str, Enum):
    INJECTION = "injection"
    SECRETS = "secrets"
    AUTH_BYPASS = "auth_bypass"
    UNSAFE_DESERIALIZATION = "unsafe_deserialization"
    LOGIC_ERROR = "logic_error"
    CODE_SMELL = "code_smell"
    UNNECESSARY_COMPLEXITY = "unnecessary_complexity"
    MISSING_TEST = "missing_test"
    UNTESTED_EDGE_CASE = "untested_edge_case"
    BRITTLE_ASSERTION = "brittle_assertion"
    COVERAGE_GAP = "coverage_gap"
    MISSING_DOCSTRING = "missing_docstring"
    OUTDATED_COMMENT = "outdated_comment"
    UNDOCUMENTED_PUBLIC_API = "undocumented_public_api"
    UNEXPLAINED_DECISION = "unexplained_decision"


class ReviewOutcome(str, Enum):
    APPROVED = "approved"
    REQUEST_CHANGES = "request_changes"
    CRITICAL_BLOCK = "critical_block"
    ESCALATED = "escalated"


class EventType(str, Enum):
    SPAN_START = "span.start"
    SPAN_END = "span.end"
    LLM_CALL = "llm.call"
    TOOL_CALL = "tool.call"
    DECISION = "decision"
    ESCALATION = "escalation"