from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.findings import Finding
from backend.models.enums import AgentType, Severity, FindingCategory
from backend.memory.context_retriever import ContextRetriever
from backend.tools.llm_client import llm_client
from backend.observability.events import SpanContext, emit_decision
from backend.reliability import with_timeout, TimeoutConfig
from backend.config import settings


class BaseAgent(ABC):
    def __init__(self, agent_type: AgentType):
        self.agent_type = agent_type

    @abstractmethod
    def get_system_prompt(self) -> str:
        pass

    @abstractmethod
    def get_focus_keywords(self) -> List[str]:
        pass

    async def review(
        self,
        session: AsyncSession,
        review_id: UUID,
        diff: str,
        repo: str,
    ) -> List[Finding]:
        async with SpanContext(session, review_id, self.agent_type):
            retriever = ContextRetriever(session)
            context = await retriever.retrieve_for_agent(repo, diff, self.agent_type.value, self.get_focus_keywords())
            
            findings = await self._analyze_with_llm(session, review_id, diff, context)
            
            await emit_decision(
                session,
                review_id,
                self.agent_type,
                outcome=None,
                confidence=sum(f.confidence for f in findings) / len(findings) if findings else 0.0,
                payload={"findings_count": len(findings)},
            )
            
            return findings

    async def _analyze_with_llm(
        self,
        session: AsyncSession,
        review_id: UUID,
        diff: str,
        context: List[str],
    ) -> List[Finding]:
        context_text = "\n\n".join([f"--- Context {i+1} ---\n{c}" for i, c in enumerate(context)])
        
        prompt = f"""{self.get_system_prompt()}

## Codebase Context
{context_text}

## Pull Request Diff
```diff
{diff}
```

Analyze the diff and return findings as a JSON array. Each finding must have:
- severity: CRITICAL|HIGH|MEDIUM|LOW|INFO
- category: (use appropriate category for your domain)
- summary: Brief description
- file_path: Path to the file
- line_start: Starting line number
- line_end: Ending line number (optional)
- suggestion: Specific fix suggestion
- confidence: 0.0-1.0
- rationale: Why this finding is valid
"""
        
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": prompt},
        ]
        
        response = await with_timeout(
            lambda: llm_client.chat_completion(
                session, review_id, self.agent_type, messages,
                response_format={"type": "json_object"},
            ),
            timeout=TimeoutConfig.LLM_CALL,
            operation=f"llm_call_{self.agent_type.value}",
        )
        
        import json
        try:
            result = json.loads(response["content"])
            findings_data = result.get("findings", [])
        except json.JSONDecodeError:
            findings_data = []
        
        findings = []
        for f in findings_data:
            finding = Finding(
                agent_type=self.agent_type,
                severity=Severity(f.get("severity", "MEDIUM")),
                category=FindingCategory(f.get("category", "code_smell")),
                summary=f.get("summary", ""),
                file_path=f.get("file_path", ""),
                line_start=f.get("line_start", 0),
                line_end=f.get("line_end"),
                suggestion=f.get("suggestion", ""),
                confidence=f.get("confidence", 0.5),
                rationale=f.get("rationale", ""),
            )
            findings.append(finding)
        
        return findings