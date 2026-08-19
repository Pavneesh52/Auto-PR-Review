from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class CapabilityScope(Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    ADMIN = "admin"


@dataclass
class Tool:
    name: str
    description: str
    function: Callable
    scope: CapabilityScope = CapabilityScope.READ_ONLY
    parameters: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self, scope: Optional[CapabilityScope] = None) -> List[Tool]:
        if scope:
            return [t for t in self._tools.values() if t.scope == scope]
        return list(self._tools.values())

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]


tool_registry = ToolRegistry()