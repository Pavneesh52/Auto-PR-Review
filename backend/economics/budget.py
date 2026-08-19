from typing import Dict, Any
from backend.config import settings
from backend.database.postgres import AsyncSessionLocal
from backend.economics.cost_repository import CostRepository
from backend.core.exceptions import BudgetExceededError
from backend.observability import get_logger

logger = get_logger(__name__)


class BudgetGuard:
    def __init__(self):
        self.daily_cost_budget = settings.daily_cost_budget_usd
        self.daily_token_budget = settings.daily_token_budget

    async def check_budget(self) -> Dict[str, Any]:
        async with AsyncSessionLocal() as session:
            cost_repo = CostRepository(session)
            status = await cost_repo.get_budget_status()
            
            if status["today_spend_usd"] >= self.daily_cost_budget:
                raise BudgetExceededError(
                    f"Daily cost budget exceeded: ${status['today_spend_usd']:.2f} / ${self.daily_cost_budget:.2f}",
                    status["today_spend_usd"],
                    self.daily_cost_budget,
                )
            
            return status

    async def check_token_budget(self, estimated_tokens: int) -> bool:
        async with AsyncSessionLocal() as session:
            cost_repo = CostRepository(session)
            status = await cost_repo.get_budget_status()
            
            # This is simplified - in reality you'd track tokens separately
            return True


budget_guard = BudgetGuard()