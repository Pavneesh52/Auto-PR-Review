import re
from typing: List, Dict, Any


class InjectionGuard:
    PROMPT_INJECTION_PATTERNS = [
        r"ignore\s+(?:previous|above|all)\s+instructions",
        r"forget\s+(?:everything|previous|above)",
        r"you\s+are\s+now\s+(?:a|an)\s+\w+",
        r"system\s*:\s*",
        r"assistant\s*:\s*",
        r"user\s*:\s*",
        r"<\|.*?\|>",
        r"```\s*(?:system|assistant|user)",
        r"###\s*(?:system|assistant|user)",
    ]
    
    CODE_INJECTION_PATTERNS = [
        r";\s*(?:rm|del|drop|truncate|delete)",
        r"(?:union|select|insert|update|delete|drop)\s+",
        r"(?:exec|execute|eval|system)\s*\(",
        r"(?:subprocess|os\.system|shell_exec)\s*\(",
    ]

    def __init__(self):
        self.prompt_patterns = [re.compile(p, re.IGNORECASE) for p in self.PROMPT_INJECTION_PATTERNS]
        self.code_patterns = [re.compile(p, re.IGNORECASE) for p in self.CODE_INJECTION_PATTERNS]

    def check_prompt_injection(self, text: str) -> List[str]:
        matches = []
        for pattern in self.prompt_patterns:
            if pattern.search(text):
                matches.append(pattern.pattern)
        return matches

    def check_code_injection(self, text: str) -> List[str]:
        matches = []
        for pattern in self.code_patterns:
            if pattern.search(text):
                matches.append(pattern.pattern)
        return matches

    def sanitize_input(self, text: str) -> str:
        return text


injection_guard = InjectionGuard()