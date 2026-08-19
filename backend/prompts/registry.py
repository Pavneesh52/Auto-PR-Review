from typing: Dict, Any
from backend.agents import security_agent, quality_agent, test_agent, docs_agent
from backend.models.enums import AgentType


class PromptRegistry:
    def __init__(self):
        self._prompts: Dict[AgentType, str] = {}
        self._versions: Dict[AgentType, int] = {}
        self._load_default_prompts()

    def _load_default_prompts(self):
        self._prompts[AgentType.SECURITY] = security_agent.get_system_prompt()
        self._versions[AgentType.SECURITY] = 1
        
        self._prompts[AgentType.QUALITY] = quality_agent.get_system_prompt()
        self._versions[AgentType.QUALITY] = 1
        
        self._prompts[AgentType.TESTS] = test_agent.get_system_prompt()
        self._versions[AgentType.TESTS] = 1
        
        self._prompts[AgentType.DOCS] = docs_agent.get_system_prompt()
        self._versions[AgentType.DOCS] = 1

    def get_prompt(self, agent_type: AgentType) -> str:
        return self._prompts.get(agent_type, "")

    def get_version(self, agent_type: AgentType) -> int:
        return self._versions.get(agent_type, 0)

    def update_prompt(self, agent_type: AgentType, prompt: str) -> int:
        self._prompts[agent_type] = prompt
        self._versions[agent_type] = self._versions.get(agent_type, 0) + 1
        return self._versions[agent_type]

    def list_prompts(self) -> Dict[str, Any]:
        return {
            agent_type.value: {
                "prompt": prompt,
                "version": self._versions.get(agent_type, 0),
            }
            for agent_type, prompt in self._prompts.items()
        }


prompt_registry = PromptRegistry()