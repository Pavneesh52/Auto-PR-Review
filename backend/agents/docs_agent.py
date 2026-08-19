from typing import List
from backend.agents.base_agent import BaseAgent
from backend.models.enums import AgentType, Severity, FindingCategory


class DocsAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.DOCS)

    def get_system_prompt(self) -> str:
        return """You are a documentation reviewer. Your job is to find missing docstrings, outdated comments, and undocumented public APIs.

Focus on:
1. Missing docstrings for public functions/classes
2. Outdated or misleading comments
3. Undocumented public APIs
4. Unexplained architectural decisions
5. Missing type hints
6. Inconsistent documentation style

Return findings as JSON with this structure:
{
  "findings": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
      "category": "missing_docstring|outdated_comment|undocumented_public_api|unexplained_decision",
      "summary": "Brief description",
      "file_path": "path/to/file.py",
      "line_start": 42,
      "line_end": 45,
      "suggestion": "Specific documentation to add",
      "confidence": 0.85,
      "rationale": "Detailed explanation"
    }
  ]
}

Only return findings with confidence >= 0.6. Be precise with line numbers."""

    def get_focus_keywords(self) -> List[str]:
        return [
            "docstring", "comment", "documentation",
            "public", "api", "interface",
            "type", "hint", "annotation",
            "decision", "architecture", "design",
            "todo", "fixme", "hack",
            "deprecated", "legacy",
        ]


docs_agent = DocsAgent()