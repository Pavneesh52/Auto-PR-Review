from typing: List, Dict, Any
from backend.evaluation.golden_dataset import GoldenPR, get_golden_dataset
from backend.orchestrator.langgraph_engine import workflow_engine
from backend.database.postgres import AsyncSessionLocal
from uuid import uuid4
from backend.observability import get_logger

logger = get_logger(__name__)


class LLMJudge:
    def __init__(self):
        pass

    async def evaluate_finding(
        self,
        predicted: Dict[str, Any],
        expected: Dict[str, Any],
    ) -> Dict[str, Any]:
        match = (
            predicted.get("agent_type") == expected.get("agent_type") and
            predicted.get("severity") == expected.get("severity") and
            predicted.get("category") == expected.get("category") and
            predicted.get("file_path") == expected.get("file_path") and
            abs(predicted.get("line_start", 0) - expected.get("line_start", 0)) <= 2
        )
        
        return {
            "match": match,
            "predicted": predicted,
            "expected": expected,
        }

    async def evaluate_pr(self, golden_pr: GoldenPR) -> Dict[str, Any]:
        async with AsyncSessionLocal() as session:
            result = await workflow_engine.execute_review(
                uuid4(), golden_pr.diff, golden_pr.repo, golden_pr.pr_number
            )
        
        predictions = result.get("findings", [])
        expected = golden_pr.expected_findings
        
        matches = 0
        for exp in expected:
            for pred in predictions:
                eval_result = await self.evaluate_finding(pred, exp)
                if eval_result["match"]:
                    matches += 1
                    break
        
        precision = matches / len(predictions) if predictions else 0
        recall = matches / len(expected) if expected else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            "golden_pr_id": golden_pr.id,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "matches": matches,
            "total_predicted": len(predictions),
            "total_expected": len(expected),
            "predictions": predictions,
        }


async def run_evaluation() -> Dict[str, Any]:
    judge = LLMJudge()
    dataset = get_golden_dataset()
    
    results = []
    for golden_pr in dataset:
        result = await judge.evaluate_pr(golden_pr)
        results.append(result)
        logger.info("evaluation_completed", **result)
    
    avg_precision = sum(r["precision"] for r in results) / len(results)
    avg_recall = sum(r["recall"] for r in results) / len(results)
    avg_f1 = sum(r["f1"] for r in results) / len(results)
    
    return {
        "overall": {
            "precision": avg_precision,
            "recall": avg_recall,
            "f1": avg_f1,
        },
        "per_pr": results,
    }