from typing import Dict, Any, Optional
from backend.tools.model_router import model_router, ModelTier
from backend.economics.budget import budget_guard
from backend.config import settings


class RoutingAdvisor:
    def __init__(self):
        self.cost_per_model = {
            "gpt-4o": {"input": 0.005 / 1000, "output": 0.015 / 1000},
            "gpt-4o-mini": {"input": 0.00015 / 1000, "output": 0.0006 / 1000},
        }

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = self.cost_per_model.get(model, self.cost_per_model["gpt-4o"])
        return (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])

    def recommend_model(self, agent_type: str, complexity: str = "medium") -> str:
        budget_status = None
        
        if complexity == "low":
            return model_router.get_model(agent_type, ModelTier.FAST)
        elif complexity == "high":
            return model_router.get_model(agent_type, ModelTier.POWERFUL)
        else:
            return model_router.get_model(agent_type, ModelTier.BALANCED)

    def should_downgrade(self) -> bool:
        return False


routing_advisor = RoutingAdvisor()