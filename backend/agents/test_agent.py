from typing import List
from backend.agents.base_agent import BaseAgent
from backend.models.enums import AgentType, Severity, FindingCategory


class TestAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.TESTS)

    def get_system_prompt(self) -> str:
        return """You are a test coverage reviewer. Your job is to find missing tests, untested edge cases, and brittle assertions.

Focus on:
1. Missing test cases for new functionality
2. Untested edge cases and error paths
3. Brittle or flaky assertions
4. Coverage gaps in critical paths
5. Test quality issues
6. Missing integration tests
7. Test isolation problems

Return findings as JSON with this structure:
{
  "findings": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
      "category": "missing_test|untested_edge_case|brittle_assertion|coverage_gap",
      "summary": "Brief description",
      "file_path": "path/to/file.py",
      "line_start": 42,
      "line_end": 45,
      "suggestion": "Specific test to add",
      "confidence": 0.85,
      "rationale": "Detailed explanation"
    }
  ]
}

Only return findings with confidence >= 0.6. Be precise with line numbers."""

    def get_focus_keywords(self) -> List[str]:
        return [
            "test", "spec", "assert", "expect",
            "mock", "stub", "fixture",
            "coverage", "branch", "path",
            "edge", "boundary", "corner",
            "error", "exception", "failure",
            "integration", "unit", "e2e",
            "flaky", "brittle", "unstable",
        ]


test_agent = TestAgent()