# PR Review Agent

Production-grade AI PR review agent — implementing the 20-phase pipeline architecture.

**Status:** Phases 1-18 and 20 complete and wired end to end. Phase 19 (multi-repo) deferred.

**Verified:** `pytest` 105 passed / 6 skipped · `mypy` clean · `ruff check` + `ruff format --check` clean.

## Architecture Overview

```
Phase 1:  Data Models & Schemas
Phase 2:  Webhook Ingestion (HMAC, Redis queue, idempotency)
Phase 3:  Context Assembly (GitHub API, smart context selection)
Phase 4:  Unified Data Layer (SQLAlchemy + Postgres)
Phase 5:  Orchestrator (LangGraph state graph)
Phase 6:  Security Agent (OWASP, SAST, secrets detection)
Phase 7:  Architecture Agent (coupling, layering, boundaries)
Phase 8:  Quality Agent (bugs, edge cases, DRY)
Phase 9:  Documentation Agent (README, docstrings, consistency)
Phase 10: Semantic Code Search (embeddings + cosine similarity)
Phase 11: Synthesis (dedup, severity sort, max-comments cap)
Phase 12: HITL Gate (approval/rejection before posting)
Phase 13: GitHub Comment Posting (format + post review comments)
Phase 14: Caching & Incremental Review (skip unchanged files)
Phase 15: CI/CD Pipeline (GitHub Actions — lint, typecheck, test, build, integration)
Phase 16: Feedback Loop (thumbs up/down feeds back into prompts)
Phase 17: Rate Limiting & Cost Control (Redis sliding window + daily token budget)
Phase 18: Monitoring & Observability (metrics endpoint + event traces)
Phase 19: (Multi-repo — deferred)
Phase 20: Deployment (Docker, Alembic migrations, env config)
```

### Pipeline Flow

```
GITHUB WEBHOOK
  POST /webhook → HMAC verify → Parse → Redis queue (idempotent)

EVENT PROCESSOR
  Dequeue → Rate limit → Daily budget check → Context assembly
    → Cache lookup (Phase 14: unchanged files reuse prior findings)
    → Feedback guidance (Phase 16: don't repeat rejected findings)
    → LangGraph pipeline
    → Persist → Record traces → Record token spend
    → HITL? → await approval   |   else → post to GitHub

LANGGRAPH PIPELINE
  context_assembly
    → [security | architecture | quality | documentation] (parallel)
    → synthesis
    → should_hitl?  yes → hitl_gate (pause)   no → END
```

## Project Structure

```
src/pr_review_agent/
├── config/settings.py           # Pydantic settings (all phases)
├── models/
│   ├── events.py                # GitHub webhook event models
│   └── review.py                # Review domain models
├── webhooks/
│   ├── hmac.py                  # HMAC-SHA256 signature verification
│   └── receiver.py              # FastAPI routes (webhook + API)
├── queue/event_queue.py         # Redis queue with idempotency
├── context/
│   ├── github_client.py         # GitHub API client
│   ├── smart_context.py         # Smart context selection
│   ├── assembly.py              # Context assembly engine
│   ├── llm_client.py            # Shared LLM client (token + cost aware)
│   └── embeddings.py            # Embedding service (Phase 10)
├── orchestrator/
│   ├── state.py                 # LangGraph ReviewState
│   ├── graph.py                 # LangGraph pipeline definition
│   └── nodes.py                 # Agents + synthesis + HITL gate
├── github/comment_poster.py     # GitHub PR review comment poster
├── db/
│   ├── connection.py            # Async SQLAlchemy engine
│   ├── models.py                # ORM models (8 tables)
│   └── repositories.py          # Data access layer
├── processor.py                 # Event processor (full pipeline)
├── rate_limiter.py              # Sliding window + daily token budget
├── app.py                       # Application entry point (lifespan)
└── cli.py                       # CLI: serve | index

migrations/versions/
├── 001_initial.py               # All tables
└── 002_review_history.py        # Allow multiple reviews per PR
```

## Setup

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Start Redis + Postgres (requires Docker Desktop running)
docker compose up -d redis postgres

# 3. Configure environment
cp .env.example .env
# Edit .env and set at minimum:
#   OPENAI_API_KEY=sk-...
#   GITHUB_WEBHOOK_SECRET=<random string you also give GitHub>
#   GITHUB_TOKEN=ghp_...      (required for posting reviews & private repos)

# 4. Create the database schema
alembic upgrade head

# 5. (Optional) Index a repo to enable semantic context selection
pr-review-agent index owner/repo

# 6. Run the server
pr-review-agent serve          # or: python -m pr_review_agent.app

# 7. Run the checks
python -m pytest tests/ -q
python -m mypy src/pr_review_agent --ignore-missing-imports
ruff check . && ruff format --check .
```

### CLI

| Command | Description |
|---------|-------------|
| `pr-review-agent serve` | Run the webhook server (default). |
| `pr-review-agent index owner/repo [--ref main] [--max-files 200]` | Embed a repository's source files for Phase 10 semantic search. |

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key for LLM agents and embeddings |
| `GITHUB_WEBHOOK_SECRET` | Yes | — | HMAC secret for webhook verification (empty = verification skipped) |
| `GITHUB_TOKEN` | Yes* | — | GitHub PAT for posting reviews and reading private repos |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection |
| `DATABASE_URL` | No | `postgresql+asyncpg://pr_agent:...@localhost:5433/pr_review_agent` | Postgres (async) |
| `DATABASE_URL_SYNC` | No | `postgresql://pr_agent:...` | Postgres (sync, for Alembic) |
| `LLM_MODEL` | No | `gpt-4o-mini` | Model for review agents |
| `MAX_COMMENTS_PER_PR` | No | `10` | Max findings per review |
| `HITL_CONFIDENCE_THRESHOLD` | No | `0.7` | Findings below this confidence pause for approval |
| `RATE_LIMIT_PER_MINUTE` | No | `30` | Global reviews/min |
| `RATE_LIMIT_PER_REPO_PER_HOUR` | No | `10` | Per-repo reviews/hour |
| `MAX_TOKENS_PER_REPO_PER_DAY` | No | `500000` | Pre-flight daily token budget per repo |
| `MAX_COST_PER_REVIEW_USD` | No | `0.50` | Post-hoc per-review cost warning threshold |
| `MAX_TOKENS_PER_REVIEW` | No | `50000` | Per-review token cap |
| `LLM_PRICE_PER_1M_INPUT_TOKENS` | No | `0.15` | USD/1M input tokens, for real cost tracking |
| `LLM_PRICE_PER_1M_OUTPUT_TOKENS` | No | `0.60` | USD/1M output tokens |
| `SEMANTIC_SEARCH_ENABLED` | No | `true` | Add semantically similar files to context |
| `SEMANTIC_SEARCH_LIMIT` | No | `5` | Max semantic matches per review |
| `CACHE_ENABLED` | No | `true` | Reuse findings for unchanged files |
| `GITHUB_COMMENT_MODE` | No | `summary` | `summary` \| `inline` \| `both` |
| `LOG_LEVEL` | No | `INFO` | Logging level |

\* Without `GITHUB_TOKEN`, posting is skipped and private repos can't be read.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/webhook` | GitHub PR webhook receiver |
| `GET` | `/reviews/{id}` | Get review with findings |
| `POST` | `/reviews/{id}/approve` | HITL approve/reject/edit **and post to GitHub** |
| `POST` | `/findings/{id}/feedback` | Submit feedback on a finding |
| `GET` | `/repos/{name}/feedback` | Aggregated feedback stats |
| `GET` | `/metrics` | Global metrics dashboard |
| `GET` | `/repos/{name}/metrics` | Per-repo metrics |

## How the key flows work

### HITL approval (Phase 12 + 13)

Synthesis escalates only when a finding's confidence is **below**
`HITL_CONFIDENCE_THRESHOLD`. The review is saved as `awaiting_approval` and
nothing is posted. When the operator calls `/reviews/{id}/approve`:

- `decision: "approved"` → stored findings posted to GitHub, review → `completed`
- `decision: "edited"` → findings from `edited_findings_json` posted, review → `completed`
- `decision: "rejected"` → nothing posted, review → `skipped`

If GitHub posting fails the endpoint returns `502` and the review **stays**
`awaiting_approval` so the decision can be retried.

### Incremental review (Phase 14)

Each changed file's patch is hashed. If a file's findings were cached for that
exact hash, the LLM findings are reused and the file is not sent to the agents.
If every file is a cache hit, the pipeline skips the LLM entirely and
synthesizes from cache.

### Cost control (Phase 17)

1. **Pre-flight:** a per-repo daily token budget is checked *before* any LLM call.
2. **Real accounting:** the LLM client returns actual prompt/completion tokens;
   cost is computed from configured per-1M pricing.
3. **Post-hoc:** token spend is recorded to Redis against the daily budget.

### Feedback loop (Phase 16)

Findings marked thumbs-down are surfaced as prompt guidance
("this repo previously rejected …") so the agents avoid repeating false positives.

## Testing

```bash
python -m pytest tests/ -q
```

Redis- and Postgres-dependent tests **skip automatically** when those services
aren't reachable, so the suite passes without Docker. Bring them up to run
the full integration set.

## Known Limitations

- **Vector search is not pgvector.** Embeddings are stored as JSON and scored
  with cosine similarity in Python. Fine for small/medium repos; a pgvector
  index is the documented upgrade path for large ones.
- **Single worker.** One event processor; no consumer groups yet.
- **`MAX_COST_PER_REVIEW_USD` is a warning**, not a hard stop (the daily token
  budget is the enforced ceiling).
- **Phase 19 (multi-repo/monorepo)** is not implemented.

## Remaining Work

- Phase 19: multi-repo & monorepo support
- pgvector index for large-repo semantic search
- Horizontal scaling (consumer groups, read replicas)
