from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    app_name: str = "AI PR Review Agent"
    debug: bool = True
    environment: str = "development"

    tiger_database_url: str = Field(..., description="Tiger Cloud Postgres connection string")
    nvidia_api_key: str = Field(..., description="NVIDIA API key for Nemotron 3 Ultra LLM")
    
    github_app_id: int = Field(..., description="GitHub App ID")
    github_webhook_secret: str = Field(..., description="GitHub webhook secret for HMAC verification")
    github_private_key_path: str = Field(..., description="Path to GitHub App private key")
    
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    
    nvidia_model: str = Field(default="nvidia/nemotron-3-ultra", description="NVIDIA Nemotron model for LLM")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", description="NVIDIA API base URL")
    
    # Local embeddings (sentence-transformers) - FREE, no API key needed
    embedding_model: str = Field(default="all-MiniLM-L6-v2", description="Local sentence-transformers model")
    embedding_dimensions: int = Field(default=384, description="Embedding dimensions (384 for all-MiniLM-L6-v2)")
    embedding_device: str = Field(default="cpu", description="Device for embeddings: cpu or cuda")
    
    daily_token_budget: int = Field(default=1000000, description="Daily token budget")
    daily_cost_budget_usd: float = Field(default=50.0, description="Daily cost budget in USD")
    confidence_threshold: float = Field(default=0.75, description="Confidence threshold for auto-post")
    
    max_concurrent_reviews: int = Field(default=10, description="Max concurrent PR reviews")
    review_timeout_seconds: int = Field(default=300, description="Timeout for review completion")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()