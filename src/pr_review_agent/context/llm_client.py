"""Shared LLM client for review agents.

All 4 agent nodes call this to get structured analysis from an LLM.
Handles prompt construction, API calls, response parsing, and — critically —
returns the real token usage so cost tracking is based on facts rather than
guesses.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog
from openai import AsyncOpenAI

from pr_review_agent.config.settings import settings
from pr_review_agent.models.review import ChangedFile

logger = structlog.get_logger(__name__)

# Model configuration
DEFAULT_MODEL = "gpt-4o-mini"
MAX_RETRIES = 2
RESPONSE_TIMEOUT = 120.0

# JSON response instruction appended to every prompt
JSON_INSTRUCTION = """
Respond ONLY with a valid JSON object in this exact format:

{
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "end_line": null,
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
      "category": "security|architecture|quality|documentation",
      "title": "Short title of the issue",
      "description": "Detailed explanation of the problem",
      "suggestion": "Concrete code fix or improvement suggestion",
      "confidence": 0.0-1.0
    }
  ]
}

Rules:
- severity must be one of: CRITICAL, HIGH, MEDIUM, LOW, INFO
- confidence is 0.0 to 1.0 (how sure you are the finding is valid)
- line/end_line refer to lines in the NEW file (post-apply)
- If no issues found, return {"findings": []}
- Do NOT include any text outside the JSON object
"""


@dataclass(slots=True)
class LLMCallResult:
    """Result of an LLM call, including real token usage.

    Token counts include every attempt, so a retry after an unparseable
    response still shows up in cost accounting.
    """

    data: dict | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = DEFAULT_MODEL
    attempts: int = 0
    error: str | None = None
    findings: list[dict] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        """Total tokens billed for this call."""
        return self.prompt_tokens + self.completion_tokens


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost from real token counts and configured pricing."""
    input_cost = (prompt_tokens / 1_000_000) * settings.llm_price_per_1m_input_tokens
    output_cost = (completion_tokens / 1_000_000) * settings.llm_price_per_1m_output_tokens
    return input_cost + output_cost


def _build_client() -> AsyncOpenAI:
    """Create the OpenAI async client."""
    api_key = settings.openai_api_key
    if not api_key:
        raise ValueError("OPENAI_API_KEY not configured. Set it in your .env file or environment.")
    return AsyncOpenAI(api_key=api_key)


def _extract_json(text: str) -> dict | None:
    """Extract JSON from an LLM response that may contain markdown fences."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("{"):
        try:
            parsed: dict = json.loads(text)
            return parsed
        except json.JSONDecodeError:
            pass

    # Try extracting from ```json ... ``` fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            fenced: dict = json.loads(match.group(1))
            return fenced
        except json.JSONDecodeError:
            pass

    # Try finding the first { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            block: dict = json.loads(text[start : end + 1])
            return block
        except json.JSONDecodeError:
            pass

    return None


async def call_llm(
    system_prompt: str,
    user_message: str,
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> LLMCallResult:
    """Call the LLM and parse the JSON response.

    Args:
        system_prompt: System message defining the agent's role.
        user_message: User message with the diff and context.
        model: Model to use (defaults to gpt-4o-mini).
        temperature: Sampling temperature (0 = deterministic).
        max_tokens: Max response tokens.

    Returns:
        LLMCallResult — `data` is the parsed JSON (None on failure), and the
        token counters reflect every attempt made.
    """
    model = model or DEFAULT_MODEL
    full_system = system_prompt + "\n" + JSON_INSTRUCTION

    result = LLMCallResult(model=model)

    try:
        client = _build_client()
    except ValueError as e:
        logger.warning("llm_client_unavailable", error=str(e))
        result.error = str(e)
        return result

    for attempt in range(1, MAX_RETRIES + 1):
        result.attempts = attempt
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=RESPONSE_TIMEOUT,
            )

            content = response.choices[0].message.content or ""
            usage = response.usage
            if usage:
                result.prompt_tokens += usage.prompt_tokens
                result.completion_tokens += usage.completion_tokens

            logger.info(
                "llm_call_completed",
                model=model,
                attempt=attempt,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                content_length=len(content),
            )

            parsed = _extract_json(content)
            if parsed is not None:
                result.data = parsed
                result.findings = parsed.get("findings", []) or []
                result.error = None
                return result

            result.error = "response was not valid JSON"
            logger.warning(
                "llm_response_not_json",
                attempt=attempt,
                content_preview=content[:200],
            )

        except Exception as e:
            result.error = str(e)
            logger.error(
                "llm_call_failed",
                attempt=attempt,
                error=str(e),
            )

    return result


def build_diff_summary(changed_files: list[ChangedFile], context_files: dict[str, str]) -> str:
    """Build a concise diff summary for agent prompts.

    Avoids sending the full raw diff (which can be huge) and instead
    provides a structured summary with file paths, stats, and patches.
    """
    parts: list[str] = []

    for f in changed_files:
        status_marker = {
            "added": "+",
            "removed": "-",
            "modified": "~",
            "renamed": "~",
        }.get(f.status, "?")

        parts.append(
            f"--- {status_marker} {f.path} "
            f"(+{f.additions} -{f.deletions}, {f.language or 'unknown'})\n"
            f"{f.patch}"
        )

    # Add context files as reference
    if context_files:
        parts.append("\n--- CONTEXT FILES (for reference only) ---")
        for path, content in list(context_files.items())[:10]:
            # Truncate long files
            truncated = content[:2000]
            if len(content) > 2000:
                truncated += "\n... (truncated)"
            parts.append(f"\n--- {path} ---\n{truncated}")

    return "\n\n".join(parts)
