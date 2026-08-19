from typing import Dict, Optional
from enum import Enum
from backend.config import settings


class ModelTier(Enum):
    FAST = "fast"
    BALANCED = "balanced"
    POWERFUL = "powerful"


MODEL_ROUTING = {
    ModelTier.FAST: "nvidia/nemotron-3-ultra",
    ModelTier.BALANCED: "nvidia/nemotron-3-ultra",
    ModelTier.POWERFUL: "nvidia/nemotron-3-ultra",
}


class ModelRouter:
    def __init__(self):
        self.current_tier = ModelTier.BALANCED
        self.model_overrides: Dict[str, str] = {}

    def get_model(self, agent_type: str, tier: Optional[ModelTier] = None) -> str:
        if agent_type in self.model_overrides:
            return self.model_overrides[agent_type]
        
        effective_tier = tier or self.current_tier
        return MODEL_ROUTING.get(effective_tier, settings.nvidia_model)

    def set_tier(self, tier: ModelTier):
        self.current_tier = tier

    def override_model(self, agent_type: str, model: str):
        self.model_overrides[agent_type] = model

    def clear_override(self, agent_type: str):
        self.model_overrides.pop(agent_type, None)


model_router = ModelRouter()