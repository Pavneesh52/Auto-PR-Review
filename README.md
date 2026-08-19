# AI PR Review Agent

A production-grade AI-powered pull request review system built with LangGraph, Tiger Cloud (TimescaleDB), and NVIDIA Nemotron 3 Ultra. Implements the architecture from [Antern's "Designing an AI Pull-Request Review Agent"](https://www.antern.co/blogs/production-grade-ai-pr-review-agent/#s-reuse).

## Architecture Overview

```
GitHub PR → Webhook → Redis/ARQ Queue → LangGraph Orchestrator → 4 Specialist Agents → Aggregator → HITL Gate → GitHub Review
                    ↓                      ↓                        ↓              ↓
               Idempotency           Parallel Fan-out         Retrieval (RAG)   Confidence-weighted
               Check                                                          Routing
```

### Core Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Orchestrator** | LangGraph | Parallel fan-out to 4 specialists, stateful workflow |
| **Specialists** | NVIDIA Nemotron 3 Ultra | Security, Quality, Tests, Docs review agents |
| **Retrieval** | Tiger Cloud + pgvector/pgvectorscale | Hybrid search (vector + FTS) with RRF fusion |
| **Queue** | Redis + ARQ | Async job processing with retries |
| **Database** | Tiger Cloud (TimescaleDB) | One store: memory (vectors), truth (reviews), time (events) |
| **Events Spine** | Hypertable + Continuous Aggregates | Audit trail, cost tracking, dashboards |
| **HITL Gate** | Confidence-weighted | Auto-approve high confidence, escalate low/critical |

## Specialist Agents

1. **Security Agent** - Injection, secrets, auth bypasses, unsafe deserialization, path traversal, crypto issues
2. **Quality Agent** - Logic errors, code smells, complexity, performance, error handling, resource leaks
3. **Tests Agent** - Missing tests, untested edge cases, brittle assertions, coverage gaps
4. **Docs Agent** - Missing docstrings, outdated comments, undocumented APIs, missing type hints

## Data Model (Single Database, Three Lanes)

```
Tiger Cloud (PostgreSQL + TimescaleDB + pgvector + pgvectorscale)
├── Memory Lane (Vector)
│   └── code_chunks (embeddings + DiskANN index)
├── Truth Lane (Relational)
│   ├── pr_review_records
│   ├── finding_records
│   ├── hitl_reviews
│   └── hitl_feedback
└── Time Lane (Hypertable)
    ├── agent_events (partitioned by day)
    ├── agent_health_1m (continuous aggregate)
    └── pr_cost_hourly (continuous aggregate)
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Tiger Cloud account (free tier: $1000 credit, 30 days, no CC)
- NVIDIA API key (from https://build.nvidia.com/)
- GitHub App (for webhook integration)

### Configuration

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

Required variables:
- `TIGER_DATABASE_URL` - Tiger Cloud connection string
- `NVIDIA_API_KEY` - NVIDIA Nemotron 3 Ultra API key
- `GITHUB_APP_ID` - GitHub App ID
- `GITHUB_WEBHOOK_SECRET` - GitHub App webhook secret
- `GITHUB_PRIVATE_KEY_PATH` - Path to GitHub App private key (.pem)

### Run with Docker Compose

```bash
docker-compose up -d
```

Services:
- **Backend API**: http://localhost:8000
- **Frontend**: http://localhost:3000
- **Redis**: localhost:6379

### Manual Run

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database schema
python run_migrations.py

# Start backend
uvicorn backend.main:app --reload

# Start worker (separate terminal)
arq backend.job_queue.WorkerSettings
```

## API Endpoints

### Reviews
- `POST /reviews/` - Create a review job
- `GET /reviews/{review_id}` - Get review with findings
- `GET /reviews/` - List reviews (paginated)
- `POST /reviews/{review_id}/run` - Execute review manually

### Human-in-the-Loop
- `GET /hitl/queue` - List pending HITL reviews
- `GET /hitl/{hitl_id}` - Get HITL review details
- `POST /hitl/{hitl_id}/decide` - Submit human decision
- `POST /hitl/{hitl_id}/feedback` - Submit finding feedback

### Economics
- `GET /economics/health` - Agent health metrics (cost, latency, p95)
- `GET /economics/costs` - Per-PR cost breakdown

### Webhook
- `POST /webhook/github` - GitHub webhook endpoint

## GitHub App Setup

1. Create GitHub App at https://github.com/settings/apps
2. Permissions:
   - Pull requests: Read & Write
   - Contents: Read
   - Metadata: Read
3. Subscribe to events: Pull request
4. Generate private key, download `.pem` file
5. Set webhook URL: `https://your-domain.com/webhook/github`
6. Copy App ID, Webhook Secret, and private key path to `.env`

## Project Structure

```
backend/
├── agents/           # 4 specialist agents + base class
├── api/              # FastAPI routers (reviews, hitl, economics, queue)
├── auth/             # Authentication dependencies
├── config.py         # Pydantic settings
├── core/             # Exceptions, workflow engine
├── data/             # Ingestion pipelines
├── database/         # SQLAlchemy models, repositories, Tiger schema
├── economics/        # Cost tracking, budget guards, routing advisor
├── evaluation/       # Golden datasets, LLM-as-judge, regression gates
├── hitl/             # Human-in-the-loop queue, escalation, feedback
├── integrations/     # GitHub client, webhook models
├── job_queue/        # ARQ worker settings
├── memory/           # Tiger client, context retriever, embedder
├── models/           # Pydantic models (findings, enums, webhook)
├── observability/    # Events spine, logging, tracing, alerting
├── orchestrator/     # LangGraph workflow, nodes, state
├── prompts/          # Prompt registry
├── reliability/      # Retry, circuit breaker, timeout, idempotency
├── security/         # Injection guards, masking, RBAC, threat model
├── tools/            # LLM client, model router, sandbox, tool registry
└── webhook_receiver/ # Webhook validation, parsing, routing
```

## Reliability Features

- **Idempotency**: Webhook deduplication via `X-GitHub-Delivery` header
- **Retries**: Exponential backoff for LLM, GitHub API, database
- **Circuit Breakers**: Per-service failure isolation
- **Timeouts**: Configured per operation type (LLM: 60s, GitHub: 30s, DB: 10s)
- **Graceful Degradation**: Failed agents don't block others; HITL fallback

## Observability

- **Events Spine**: Every action → `agent_events` hypertable (span, LLM call, tool call, decision)
- **Structured Logging**: JSON logs with structlog
- **Cost Tracking**: Per-agent, per-PR, daily rollups via continuous aggregates
- **Dashboards**: Agent health (p95 latency, cost, rejection rate), PR cost breakdown

## Security

- **Prompt Injection Guard**: Pattern-based detection in diffs and context
- **Code Injection Guard**: SQL/command injection pattern detection
- **HMAC Verification**: GitHub webhook signature validation
- **RBAC**: Role-based access for HITL decisions

## License

MIT