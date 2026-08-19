from typing: Dict, Any
from backend.evaluation.judge import run_evaluation
from backend.observability import get_logger

logger = get_logger(__name__)


REGRESSION_THRESHOLDS = {
    "precision": 0.7,
    "recall": 0.6,
    "f1": 0.65,
}


async def check_regression() -> Dict[str, Any]:
    results = await run_evaluation()
    
    overall = results["overall"]
    passed = True
    failures = []
    
    for metric, threshold in REGRESSION_THRESHOLDS.items():
        if overall[metric] < threshold:
            passed = False
            failures.append(f"{metric}: {overall[metric]:.2f} < {threshold}")
    
    result = {
        "passed": passed,
        "metrics": overall,
        "failures": failures,
    }
    
    if passed:
        logger.info("regression_gate_passed", **overall)
    else:
        logger.error("regression_gate_failed", **result)
    
    return result


def regression_gate_decorator(func):
    async def wrapper(*args, **kwargs):
        gate_result = await check_regression()
        if not gate_result["passed"]:
            raise RuntimeError(f"Regression gate failed: {gate_result['failures']}")
        return await func(*args, **kwargs)
    return wrapper