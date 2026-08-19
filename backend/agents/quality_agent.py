from typing import List
from backend.agents.base_agent import BaseAgent
from backend.models.enums import AgentType, Severity, FindingCategory


class QualityAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.QUALITY)

    def get_system_prompt(self) -> str:
        return """You are a code quality reviewer. Your job is to find logic errors, code smells, and unnecessary complexity.

Focus on:
1. Logic errors and bugs
2. Code smells (long functions, duplicate code, etc.)
3. Unnecessary complexity
4. Performance issues
5. Error handling gaps
6. Resource leaks
7. Thread safety issues
8. API design issues

Return findings as JSON with this structure:
{
  "findings": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
      "category": "logic_error|code_smell|unnecessary_complexity",
      "summary": "Brief description",
      "file_path": "path/to/file.py",
      "line_start": 42,
      "line_end": 45,
      "suggestion": "Specific fix",
      "confidence": 0.85,
      "rationale": "Detailed explanation"
    }
  ]
}

Only return findings with confidence >= 0.6. Be precise with line numbers."""

    def get_focus_keywords(self) -> List[str]:
        return [
            "bug", "error", "exception", "crash",
            "complex", "nested", "cyclomatic",
            "duplicate", "copy", "paste",
            "performance", "slow", "optimize",
            "memory", "leak", "resource",
            "thread", "concurrent", "race",
            "api", "interface", "contract",
            "null", "none", "undefined",
        ]


quality_agent = QualityAgent()