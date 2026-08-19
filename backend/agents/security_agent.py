from typing import List
from backend.agents.base_agent import BaseAgent
from backend.models.enums import AgentType, Severity, FindingCategory


class SecurityAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.SECURITY)

    def get_system_prompt(self) -> str:
        return """You are a security-focused code reviewer. Your job is to find security vulnerabilities in pull requests.

Focus on:
1. Injection vulnerabilities (SQL, command, LDAP, XSS)
2. Secrets exposure (API keys, passwords, tokens)
3. Authentication/authorization bypasses
4. Unsafe deserialization
5. Path traversal
6. Insecure cryptography
7. Missing input validation
8. Information disclosure

Return findings as JSON with this structure:
{
  "findings": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
      "category": "injection|secrets|auth_bypass|unsafe_deserialization",
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
            "sql", "query", "execute", "cursor",
            "password", "secret", "token", "api_key", "apikey",
            "auth", "login", "permission", "role",
            "pickle", "yaml", "deserialize", "load",
            "eval", "exec", "subprocess", "shell",
            "path", "traversal", "..",
            "crypto", "encrypt", "decrypt", "hash",
            "validate", "sanitize", "escape",
        ]


security_agent = SecurityAgent()