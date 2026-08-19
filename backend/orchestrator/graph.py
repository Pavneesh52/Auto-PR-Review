from langgraph.graph import StateGraph, END
from backend.orchestrator.state import ReviewState
from backend.orchestrator.nodes import (
    security_node,
    quality_node,
    tests_node,
    docs_node,
    aggregator_node,
    hitl_gate_node,
    error_handler_node,
)
from backend.database.postgres import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession


def create_review_graph() -> StateGraph:
    workflow = StateGraph(ReviewState)
    
    workflow.add_node("security", security_node)
    workflow.add_node("quality", quality_node)
    workflow.add_node("tests", tests_node)
    workflow.add_node("docs", docs_node)
    workflow.add_node("aggregator", aggregator_node)
    workflow.add_node("hitl_gate", hitl_gate_node)
    workflow.add_node("error_handler", error_handler_node)
    
    workflow.set_entry_point("security")
    
    workflow.add_edge("security", "quality")
    workflow.add_edge("quality", "tests")
    workflow.add_edge("tests", "docs")
    workflow.add_edge("docs", "aggregator")
    workflow.add_edge("aggregator", "hitl_gate")
    workflow.add_edge("hitl_gate", END)
    
    workflow.add_conditional_edges(
        "security",
        lambda state: "error_handler" if state.error else "quality",
    )
    workflow.add_conditional_edges(
        "quality",
        lambda state: "error_handler" if state.error else "tests",
    )
    workflow.add_conditional_edges(
        "tests",
        lambda state: "error_handler" if state.error else "docs",
    )
    workflow.add_conditional_edges(
        "docs",
        lambda state: "error_handler" if state.error else "aggregator",
    )
    workflow.add_conditional_edges(
        "aggregator",
        lambda state: "error_handler" if state.error else "hitl_gate",
    )
    
    return workflow


async def run_review_workflow(review_state: ReviewState) -> ReviewState:
    graph = create_review_graph()
    app = graph.compile()
    
    async with AsyncSessionLocal() as session:
        result = await app.ainvoke(review_state, config={"configurable": {"session": session}})
    
    return result