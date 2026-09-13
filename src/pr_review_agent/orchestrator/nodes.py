"""LangGraph node functions.

Phases 5-9 — Each node is a function that reads from ReviewState,
does its work, and returns a dict of state updates.

Phases 6-9: Security, Architecture, Quality, Documentation agents
use an LLM to analyze the diff and context, returning structured findings.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog

from pr_review_agent.config.settings import settings
from pr_review_agent.context.llm_client import (
    LLMCallResult,
    build_diff_summary,
    call_llm,
    estimate_cost_usd,
)
from pr_review_agent.models.review import (
    AgentResult,
    FindingSeverity,
    ReviewFinding,
    ReviewStatus,
)
from pr_review_agent.orchestrator.state import ReviewState

logger = structlog.get_logger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────

SEVERITY_MAP = {
    "CRITICAL": FindingSeverity.CRITICAL,
    "HIGH": FindingSeverity.HIGH,
    "MEDIUM": FindingSeverity.MEDIUM,
    "LOW": FindingSeverity.LOW,
    "INFO": FindingSeverity.INFO,
}

SEVERITY_ORDER = {
    FindingSeverity.CRITICAL: 0,
    FindingSeverity.HIGH: 1,
    FindingSeverity.MEDIUM: 2,
    FindingSeverity.LOW: 3,
    FindingSeverity.INFO: 4,
}


def _parse_findings(result: LLMCallResult, agent_type: str) -> list[ReviewFinding]:
    """Parse an LLM response into ReviewFinding objects."""
    if not result.findings:
        return []

    findings: list[ReviewFinding] = []
    for item in result.findings:
        try:
            severity_str = str(item.get("severity", "INFO")).upper()
            severity = SEVERITY_MAP.get(severity_str, FindingSeverity.INFO)
            confidence = float(item.get("confidence", 0.8))
            confidence = max(0.0, min(1.0, confidence))

            findings.append(
                ReviewFinding(
                    file=item.get("file", "unknown"),
                    line=item.get("line"),
                    end_line=item.get("end_line"),
                    severity=severity,
                    category=agent_type,
                    title=item.get("title", "Untitled finding"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", ""),
                    confidence=confidence,
                    source_agent=agent_type,
                )
            )
        except Exception as e:
            logger.warning(
                "failed_to_parse_finding",
                agent_type=agent_type,
                error=str(e),
                item=item,
            )

    return findings


# ─── Context Assembly Node ────────────────────────────────────────────


async def context_assembly_node(state: ReviewState) -> dict:
    """Assemble review context from the ReviewContext object.

    This node receives the context already assembled by Phase 3's
    ContextAssembler and maps it into the graph state.
    """
    logger.info(
        "context_assembly_node",
        review_id=state.get("review_id"),
        files_changed=len(state.get("changed_files", [])),
    )

    # Validate we have diff content
    if not state.get("diff") and not state.get("changed_files"):
        return {
            "error": "No diff content available for review",
            "status": ReviewStatus.FAILED.value,
        }

    return {"status": ReviewStatus.IN_PROGRESS.value}


# ─── Generic Agent Runner ─────────────────────────────────────────────


def _build_user_message(state: ReviewState, *, include_body: bool = False) -> str:
    """Build the shared user message for an agent prompt."""
    parts = [
        f"Repository: {state.get('repository_full_name', 'unknown')}",
        f"PR #{state.get('pr_number', 0)}: {state.get('title', '')}",
        f"Author: {state.get('author', 'unknown')}",
    ]
    if include_body:
        parts.append(f"Body: {state.get('body', '')}")

    guidance = state.get("feedback_guidance", "")
    if guidance:
        parts.append(guidance)

    diff_summary = build_diff_summary(
        state.get("changed_files", []),
        state.get("context_files", {}),
    )
    parts.append(f"\nChanged files and diff:\n{diff_summary or '(no changed files)'}")
    return "\n".join(parts)


async def _run_agent(
    state: ReviewState,
    agent_type: str,
    system_prompt: str,
    *,
    include_body: bool = False,
) -> dict:
    """Run one LLM review agent and return its state update.

    Shared by all four agents so token accounting, error handling and
    prompt construction stay consistent.
    """
    start = time.monotonic()
    tokens_used = 0
    prompt_tokens = 0
    completion_tokens = 0
    findings: list[ReviewFinding] = []
    error: str | None = None

    # If context assembly already failed there is nothing to review. Bail out
    # instead of spending four LLM calls on an empty diff.
    if state.get("status") == ReviewStatus.FAILED.value or state.get("error"):
        logger.info(
            f"{agent_type}_agent_skipped",
            review_id=state.get("review_id"),
            reason="context_assembly_failed",
        )
        return {
            "agent_results": {
                **state.get("agent_results", {}),
                agent_type: AgentResult(
                    agent_type=agent_type,
                    findings=[],
                    error=state.get("error") or "context assembly failed",
                ),
            }
        }

    try:
        user_message = _build_user_message(state, include_body=include_body)
        result = await call_llm(system_prompt=system_prompt, user_message=user_message)

        tokens_used = result.total_tokens
        prompt_tokens = result.prompt_tokens
        completion_tokens = result.completion_tokens
        findings = _parse_findings(result, agent_type)

        if result.data is None:
            error = result.error or "LLM call produced no parseable response"
    except Exception as e:
        error = str(e)
        logger.error(
            f"{agent_type}_agent_error",
            review_id=state.get("review_id"),
            error=str(e),
        )

    duration = time.monotonic() - start
    logger.info(
        f"{agent_type}_agent_completed",
        review_id=state.get("review_id"),
        findings=len(findings),
        tokens=tokens_used,
        duration=f"{duration:.2f}s",
    )

    agent_result = AgentResult(
        agent_type=agent_type,
        findings=findings,
        confidence=_avg_confidence(findings),
        tokens_used=tokens_used,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        duration_seconds=duration,
        error=error,
    )

    return {
        "agent_results": {**state.get("agent_results", {}), agent_type: agent_result},
    }


# ─── Security Agent Node (Phase 6) ────────────────────────────────────

SECURITY_SYSTEM_PROMPT = """You are a senior application security engineer performing a code review.

Your focus is on security vulnerabilities. Check for:

**OWASP Top 10:**
- A01 Broken Access Control (IDOR, privilege escalation, missing auth checks)
- A02 Cryptographic Failures (weak algorithms, hardcoded keys, insecure TLS)
- A03 Injection (SQL injection, command injection, XSS, template injection)
- A04 Insecure Design (missing rate limiting, insecure defaults)
- A05 Security Misconfiguration (debug mode, verbose errors, open CORS)
- A06 Vulnerable Components (known CVEs in imports)
- A07 Auth Failures (weak passwords, session fixation, missing MFA)
- A08 Data Integrity Failures (unsigned updates, insecure deserialization)
- A09 Logging Failures (missing audit logs, sensitive data in logs)
- A10 SSRF (server-side request forgery, unvalidated URLs)

**Secrets Detection:**
- Hardcoded API keys, tokens, passwords, connection strings
- Private keys committed to source code
- Credentials in config files or environment variables committed to VCS

**SAST Patterns:**
- Unsafe use of eval(), exec(), subprocess with shell=True
- SQL string interpolation instead of parameterized queries
- Path traversal vulnerabilities
- Insecure random number generation for security purposes
- Unsafe YAML/JSON deserialization
- Missing input validation on user-controlled data

Only report genuine security issues. Do NOT report style preferences or minor code quality items."""


async def security_agent_node(state: ReviewState) -> dict:
    """Security-focused review agent (Phase 6).

    Uses LLM to scan for OWASP Top 10, secrets, and SAST patterns.
    """
    return await _run_agent(state, "security", SECURITY_SYSTEM_PROMPT)


# ─── Architecture Agent Node (Phase 7) ────────────────────────────────

ARCHITECTURE_SYSTEM_PROMPT = """\
You are a senior software architect reviewing code for structural quality.

Your focus is on architecture and design patterns. Check for:

**Coupling & Dependencies:**
- Circular imports or dependency cycles between modules
- God classes/modules that do too much
- Tight coupling between unrelated concerns (e.g., DB logic in handlers)
- Missing abstraction boundaries between layers

**Layering Violations:**
- Business logic leaking into controllers/handlers
- Direct DB access from UI/API layers (bypassing service layer)
- Domain models depending on infrastructure code
- Reverse dependencies (domain depending on framework)

**Module Boundaries:**
- Public API surface that shouldn't be exposed
- Internal implementation details leaking through interfaces
- Missing or broken encapsulation
- Incorrect module-level responsibilities

**Design Patterns:**
- Misuse of singleton, factory, or strategy patterns
- Missing dependency injection where it would improve testability
- Over-engineering (YAGNI violations)
- Under-engineering (copy-paste patterns that should be abstracted)

**Separation of Concerns:**
- Mixed business logic with I/O operations
- Configuration coupled with business logic
- Presentation mixed with data access

Only report genuine architectural concerns that affect maintainability,
scalability, or testability. Do NOT report style or formatting issues."""


async def architecture_agent_node(state: ReviewState) -> dict:
    """Architecture-focused review agent (Phase 7).

    Uses LLM to analyze coupling, layering, and module boundaries.
    """
    return await _run_agent(state, "architecture", ARCHITECTURE_SYSTEM_PROMPT)


# ─── Quality Agent Node (Phase 8) ─────────────────────────────────────

QUALITY_SYSTEM_PROMPT = """\
You are a senior code reviewer focused on code quality, correctness, and best practices.

Your focus is on code quality. Check for:

**Bug Risk:**
- Off-by-one errors, null/None dereference
- Race conditions in concurrent code
- Resource leaks (unclosed files, connections, unclosed async contexts)
- Unhandled exceptions that could crash the application
- Incorrect error handling (silently swallowing exceptions)
- Mutable default arguments

**Edge Cases:**
- Missing boundary checks (empty lists, zero division, empty strings)
- Unhandled None/null values where they could appear
- Integer overflow or precision loss
- Timezone-naive datetime comparisons
- Unicode/encoding issues in string handling

**Code Quality:**
- Functions that are too long (>50 lines) or do too many things
- Dead code or unreachable branches
- Magic numbers/strings that should be constants
- Missing type hints on public APIs
- DRY violations (copy-pasted logic)
- Unnecessary complexity (could be simplified)

**Testing Concerns:**
- Missing error-path testing
- No tests for new public functions/classes
- Test code that depends on execution order
- Missing edge case coverage

**Performance (obvious issues only):**
- O(n²) loops on large datasets where O(n) is trivial
- N+1 query patterns in database access
- Unnecessary deep copies or repeated computation
- Missing async/await where blocking I/O is called

Only report issues that would realistically cause bugs, reduce maintainability,
or create technical debt. Do NOT report pure style preferences."""


async def quality_agent_node(state: ReviewState) -> dict:
    """Code quality review agent (Phase 8).

    Uses LLM to check for bugs, edge cases, and quality issues.
    """
    return await _run_agent(state, "quality", QUALITY_SYSTEM_PROMPT)


# ─── Documentation Agent Node (Phase 9) ───────────────────────────────

DOCUMENTATION_SYSTEM_PROMPT = """You are a technical writer and documentation reviewer.

Your focus is on documentation quality and consistency. Check for:

**README & Onboarding:**
- Missing or outdated README sections (setup, usage, API docs)
- Instructions that don't match the actual code
- Missing dependency installation steps
- Incorrect environment variable documentation

**API Documentation:**
- Public functions/classes missing docstrings
- Missing parameter documentation (types, defaults, required)
- Missing return value documentation
- Missing exception/error documentation
- Outdated or incorrect examples

**Code Comments:**
- Missing comments on complex algorithms or business logic
- Outdated comments that no longer match the code
- Misleading comments (comments that say the opposite of what code does)
- Over-commented obvious code (wasted signal)

**Changelog & Versioning:**
- Missing changelog entries for breaking changes
- Inconsistent version bumping
- Missing migration notes for API changes

**In-Code Documentation:**
- Missing type annotations on public APIs
- Missing `Raises:` section in docstrings for functions with exceptions
- Missing `Args:` / `Parameters:` sections with parameter descriptions
- Missing `Returns:` section

Only report documentation issues that would realistically confuse developers
or cause bugs from misunderstanding. Do NOT report formatting preferences."""


async def documentation_agent_node(state: ReviewState) -> dict:
    """Documentation review agent (Phase 9).

    Uses LLM to check README, docstrings, and changelog consistency.
    """
    return await _run_agent(state, "documentation", DOCUMENTATION_SYSTEM_PROMPT, include_body=True)


# ─── Synthesis (Phase 11) ─────────────────────────────────────────────


def synthesize(
    agent_results: dict[str, AgentResult],
    extra_findings: list[ReviewFinding] | None = None,
) -> dict:
    """Merge findings from all agents into a final review result.

    Pure function so it can be reused without running the graph (for
    example when every changed file was served from the Phase 14 cache).

    Args:
        agent_results: Per-agent results keyed by agent type.
        extra_findings: Findings reused from cache, merged in as-is.

    Returns:
        A dict of state updates (findings, counts, summary, cost, HITL flag).
    """
    all_findings: list[ReviewFinding] = []

    for result in agent_results.values():
        if isinstance(result, AgentResult):
            all_findings.extend(result.findings)

    if extra_findings:
        all_findings.extend(extra_findings)

    # Deduplicate by (file, line, category), keeping the most severe
    seen: set[tuple[str, int | None, str]] = set()
    deduplicated: list[ReviewFinding] = []

    sorted_all = sorted(all_findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 5))

    for finding in sorted_all:
        key = (finding.file, finding.line, finding.category)
        if key not in seen:
            seen.add(key)
            deduplicated.append(finding)

    # Apply max comments cap
    capped = deduplicated[: settings.max_comments_per_pr]

    # Count by severity
    critical = sum(1 for f in capped if f.severity == FindingSeverity.CRITICAL)
    high = sum(1 for f in capped if f.severity == FindingSeverity.HIGH)
    medium = sum(1 for f in capped if f.severity == FindingSeverity.MEDIUM)
    low = sum(1 for f in capped if f.severity == FindingSeverity.LOW)

    # Generate summary
    total = len(capped)
    if total == 0:
        summary = "No issues found. LGTM! 🎉"
    else:
        parts = []
        if critical:
            parts.append(f"{critical} critical")
        if high:
            parts.append(f"{high} high")
        if medium:
            parts.append(f"{medium} medium")
        if low:
            parts.append(f"{low} low")
        summary = f"Found {total} issue{'s' if total != 1 else ''} ({', '.join(parts)})"

    # Escalate only when a finding is genuinely uncertain. The threshold is
    # configurable so a bot can auto-post when it is confident.
    needs_hitl = any(f.confidence < settings.hitl_confidence_threshold for f in capped)

    # Cost from real token usage
    total_tokens = sum(r.tokens_used for r in agent_results.values() if isinstance(r, AgentResult))
    total_prompt = sum(
        r.prompt_tokens for r in agent_results.values() if isinstance(r, AgentResult)
    )
    total_completion = sum(
        r.completion_tokens for r in agent_results.values() if isinstance(r, AgentResult)
    )
    estimated_cost = estimate_cost_usd(total_prompt, total_completion)

    return {
        "all_findings": all_findings,
        "deduplicated_findings": deduplicated,
        "sorted_findings": capped,
        "summary": summary,
        "total_comments": total,
        "critical_count": critical,
        "high_count": high,
        "medium_count": medium,
        "low_count": low,
        "total_tokens": total_tokens,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "estimated_cost_usd": estimated_cost,
        "should_escalate_to_hitl": needs_hitl,
        "status": ReviewStatus.COMPLETED.value,
    }


async def synthesis_node(state: ReviewState) -> dict:
    """Synthesize and deduplicate findings from all agents.

    Phase 11 — merges overlapping findings, sorts by severity,
    applies the max-comments cap.
    """
    # Never let synthesis paper over an upstream failure with a green status.
    if state.get("status") == ReviewStatus.FAILED.value:
        logger.warning(
            "synthesis_skipped_after_failure",
            review_id=state.get("review_id"),
            error=state.get("error"),
        )
        return {
            "status": ReviewStatus.FAILED.value,
            "error": state.get("error") or "review pipeline failed",
            "all_findings": [],
            "deduplicated_findings": [],
            "sorted_findings": [],
            "summary": "",
            "total_comments": 0,
            "should_escalate_to_hitl": False,
        }

    updates = synthesize(
        state.get("agent_results", {}),
        state.get("cached_findings", []),
    )

    logger.info(
        "synthesis_completed",
        review_id=state.get("review_id"),
        total_raw=len(updates["all_findings"]),
        deduplicated=len(updates["deduplicated_findings"]),
        final=updates["total_comments"],
        needs_hitl=updates["should_escalate_to_hitl"],
    )

    updates["completed_at"] = datetime.now(UTC)
    return updates


# ─── HITL Gate Node ───────────────────────────────────────────────────


async def hitl_gate_node(state: ReviewState) -> dict:
    """Human-in-the-loop gate node.

    Phase 12 — Sets the review status to awaiting_approval and logs
    the escalation. The actual approval/rejection is handled by the
    processor via the /reviews/{id}/approve endpoint.

    This node marks the graph as complete, and the processor
    detects the awaiting_approval status to skip GitHub posting.
    """
    logger.info(
        "hitl_gate_triggered",
        review_id=state.get("review_id"),
        total_comments=state.get("total_comments", 0),
    )

    # Find the lowest-confidence finding for context
    low_confidence_findings = []
    for f in state.get("sorted_findings", []):
        if f.confidence < settings.hitl_confidence_threshold:
            low_confidence_findings.append(
                {
                    "file": f.file,
                    "line": f.line,
                    "title": f.title,
                    "confidence": f.confidence,
                }
            )

    logger.info(
        "hitl_escalation_details",
        review_id=state.get("review_id"),
        low_confidence_count=len(low_confidence_findings),
        findings=low_confidence_findings,
    )

    return {
        "status": ReviewStatus.AWAITING_APPROVAL.value,
        "error": None,
    }


# ─── Helpers ──────────────────────────────────────────────────────────


def _avg_confidence(findings: list[ReviewFinding]) -> float:
    """Calculate average confidence across findings."""
    if not findings:
        return 0.0
    return sum(f.confidence for f in findings) / len(findings)


# ─── Conditional Edge: Should HITL? ──────────────────────────────────
def should_escalate(state: ReviewState) -> str:
    """Router function: should we pause for human review?

    Returns:
        "hitl" if findings need human approval (low confidence)
        "done" if we can auto-approve
    """
    if state.get("should_escalate_to_hitl", False):
        return "hitl"
    return "done"
