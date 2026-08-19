from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from backend.config import settings
from backend.tools.model_router import model_router, ModelTier
from backend.observability.events import emit_llm_call
from backend.reliability import with_timeout, TimeoutConfig
from backend.core.exceptions import LLMError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from backend.models.enums import AgentType
import time


class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
        )

    async def chat_completion(
        self,
        session: AsyncSession,
        review_id: UUID,
        agent: AgentType,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        tier: Optional[ModelTier] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        model_name = model or model_router.get_model(agent.value, tier)
        
        start_time = time.time()
        try:
            response = await with_timeout(
                lambda: self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                ),
                timeout=TimeoutConfig.LLM_CALL,
                operation=f"llm_call_{agent.value}",
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            tokens_in = response.usage.prompt_tokens
            tokens_out = response.usage.completion_tokens
            cost_usd = self._calculate_cost(model_name, tokens_in, tokens_out)
            
            await emit_llm_call(
                session,
                review_id,
                agent,
                model_name,
                tokens_in,
                tokens_out,
                cost_usd,
                latency_ms,
                payload={"messages_count": len(messages)},
            )
            
            return {
                "content": response.choices[0].message.content,
                "model": model_name,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "latency_ms": latency_ms,
            }
        
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            await emit_llm_call(
                session,
                review_id,
                agent,
                model_name,
                0,
                0,
                0.0,
                latency_ms,
                payload={"error": str(e)},
            )
            raise LLMError(f"LLM call failed: {e}", model_name)

    def _calculate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        pricing = {
            "nvidia/nemotron-3-ultra": {"input": 0.0, "output": 0.0},
            "nvidia/nemotron-3-ultra-550b": {"input": 0.0, "output": 0.0},
        }
        
        model_pricing = pricing.get(model, {"input": 0.0, "output": 0.0})
        return (tokens_in * model_pricing["input"]) + (tokens_out * model_pricing["output"])


llm_client = LLMClient()