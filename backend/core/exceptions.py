class ReviewAgentError(Exception):
    def __init__(self, message: str, code: str = "REVIEW_ERROR", details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class WebhookValidationError(ReviewAgentError):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "WEBHOOK_VALIDATION_ERROR", details)


class IdempotencyError(ReviewAgentError):
    def __init__(self, message: str, delivery_id: str):
        super().__init__(message, "IDEMPOTENCY_ERROR", {"delivery_id": delivery_id})


class LLMError(ReviewAgentError):
    def __init__(self, message: str, model: str, details: dict = None):
        super().__init__(message, "LLM_ERROR", {"model": model, **(details or {})})


class RetrievalError(ReviewAgentError):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "RETRIEVAL_ERROR", details)


class DatabaseError(ReviewAgentError):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "DATABASE_ERROR", details)


class BudgetExceededError(ReviewAgentError):
    def __init__(self, message: str, current_spend: float, budget: float):
        super().__init__(message, "BUDGET_EXCEEDED", {"current_spend": current_spend, "budget": budget})


class HITLError(ReviewAgentError):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "HITL_ERROR", details)


class GitHubAPIError(ReviewAgentError):
    def __init__(self, message: str, status_code: int, details: dict = None):
        super().__init__(message, "GITHUB_API_ERROR", {"status_code": status_code, **(details or {})})


class OrchestrationError(ReviewAgentError):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "ORCHESTRATION_ERROR", details)