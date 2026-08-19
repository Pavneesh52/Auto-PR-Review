from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from backend.config import settings
from backend.database.postgres import init_tiger_schema
from backend.api import (
    reviews_router,
    economics_router,
    hitl_router,
    queue_router,
)
from backend.webhook_receiver import route_webhook
from backend.observability import setup_tracing, get_logger
from backend.orchestrator.langgraph_engine import workflow_engine

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup")
    
    try:
        await init_tiger_schema()
        logger.info("database_schema_initialized")
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))
    
    setup_tracing(app)
    logger.info("tracing_configured")
    
    yield
    
    logger.info("application_shutdown")


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reviews_router)
app.include_router(economics_router)
app.include_router(hitl_router)
app.include_router(queue_router)


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_delivery: str = Header(...),
    x_hub_signature_256: str = Header(...),
    x_github_event: str = Header(...),
):
    payload = await request.body()
    
    result = await route_webhook(payload, x_hub_signature_256, x_github_delivery)
    return result


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/")
async def root():
    return {"message": "AI PR Review Agent", "version": "1.0.0"}