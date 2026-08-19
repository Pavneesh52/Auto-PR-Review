from typing import Optional
from backend.config import settings
import structlog

logger = structlog.get_logger()


class AlertManager:
    def __init__(self):
        self.alert_channels = {}

    async def send_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "warning",
        metadata: Optional[dict] = None,
    ):
        alert = {
            "type": alert_type,
            "message": message,
            "severity": severity,
            "metadata": metadata or {},
        }
        logger.warning("alert_triggered", **alert)
        
        if severity == "critical":
            await self._send_critical_alert(alert)

    async def _send_critical_alert(self, alert: dict):
        pass

    async def check_budget_alert(self, current_spend: float, budget: float):
        percentage = (current_spend / budget) * 100 if budget > 0 else 0
        if percentage >= 100:
            await self.send_alert(
                "budget_exceeded",
                f"Daily budget exceeded: ${current_spend:.2f} / ${budget:.2f}",
                "critical",
                {"current_spend": current_spend, "budget": budget, "percentage": percentage},
            )
        elif percentage >= 80:
            await self.send_alert(
                "budget_warning",
                f"Daily budget at {percentage:.0f}%: ${current_spend:.2f} / ${budget:.2f}",
                "warning",
                {"current_spend": current_spend, "budget": budget, "percentage": percentage},
            )

    async def check_escalation_rate(self, escalation_count: int, total_reviews: int):
        if total_reviews == 0:
            return
        rate = escalation_count / total_reviews
        if rate > 0.5:
            await self.send_alert(
                "high_escalation_rate",
                f"Escalation rate at {rate:.0%}: {escalation_count}/{total_reviews}",
                "warning",
                {"escalation_count": escalation_count, "total_reviews": total_reviews, "rate": rate},
            )

    async def check_agent_failure_rate(self, agent: str, failure_count: int, total_calls: int):
        if total_calls == 0:
            return
        rate = failure_count / total_calls
        if rate > 0.1:
            await self.send_alert(
                "agent_failure_rate",
                f"Agent {agent} failure rate at {rate:.0%}: {failure_count}/{total_calls}",
                "warning",
                {"agent": agent, "failure_count": failure_count, "total_calls": total_calls, "rate": rate},
            )


alert_manager = AlertManager()