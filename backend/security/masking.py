import re
from typing: Dict, Any


class SecretMasker:
    PATTERNS = [
        (re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*[\w-]+'), r'\1=***MASKED***'),
        (re.compile(r'(?i)(secret|password|passwd|pwd)\s*[:=]\s*[\w!@#$%^&*()_+-=]+'), r'\1=***MASKED***'),
        (re.compile(r'(?i)(token|bearer)\s*[:=]\s*[\w.-]+'), r'\1=***MASKED***'),
        (re.compile(r'(?i)(access[_-]?key|accesskey)\s*[:=]\s*[\w]+'), r'\1=***MASKED***'),
        (re.compile(r'(?i)(private[_-]?key|privatekey)\s*[:=]\s*[\w-]+'), r'\1=***MASKED***'),
        (re.compile(r'sk-[\w-]{20,}'), r'sk-***MASKED***'),
        (re.compile(r'gh[pousr]_[A-Za-z0-9_]{36,}'), r'gh***MASKED***'),
        (re.compile(r'xox[baprs]-[\w-]+'), r'xox-***MASKED***'),
    ]

    def mask_secrets(self, text: str) -> str:
        result = text
        for pattern, replacement in self.PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    def mask_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.mask_secrets(value)
            elif isinstance(value, dict):
                result[key] = self.mask_dict(value)
            elif isinstance(value, list):
                result[key] = [self.mask_secrets(v) if isinstance(v, str) else v for v in value]
            else:
                result[key] = value
        return result


secret_masker = SecretMasker()