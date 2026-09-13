# Architecture Document — PR Review Agent

## System Overview

The PR Review Agent is an automated code review system that ingests GitHub pull requests, analyzes them with multiple specialized AI agents, and posts structured review comments back to GitHub.

```
                    ┌──────────────────────┐
                    │       GitHub         │
                    │  (Webhook Source)    │
                    └──────────┬───────────┘
                               │ POST /webhook
                    ┌──────────▼───────────┐
                    │    FastAPI Server     │
                    │  ┌────────────────┐  │
                    │  │ HMAC Verify    │  │
                    │  │ Payload Parse  │  │
                    │  │ Idempotency    │  │
                    │  └────────────────┘  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │     Redis Queue      │
                    │  (BLPOP + Dedup)     │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Event Processor    │
                    │  (Background Task)   │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │ Rate Limiter   │ │  Context    │ │   Cache     │
    │ (Redis)        │ │  Assembly   │ │  (Postgres) │
    └────────────────┘ └──────┬──────┘ └─────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  LangGraph Pipeline │
                    │                     │
                    │  ┌───────────────┐  │
                    │  │   Context     │  │
                    │  │   Assembly    │  │
                    │  └───────┬───────┘  │
                    │          │          │
                    │    ┌─────┴─────┐    │
                    │    │ Parallel  │    │
                    │    │  Agents   │    │
                    │    └─────┬─────┘    │
                    │          │          │
                    │  ┌───────▼───────┐  │
                    │  │   Synthesis   │  │
                    │  └───────┬───────┘  │
                    │          │          │
                    │  ┌───────▼───────┐  │
                    │  │  HITL Gate?   │  │
                    │  └───────┬───────┘  │
                    │          │          │
                    └──────────┼──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │   Postgres     │ │   GitHub    │ │  Metrics    │
    │  (Persist)     │ │  (Post)     │ │  (Log)      │
    └────────────────┘ └─────────────┘ └─────────────┘
```

## Component Details

### 1. Webhook Receiver (Phase 2)

**File:** `webhooks/receiver.py`

The entry point. Receives GitHub webhook POST requests and:

1. Verifies HMAC-SHA256 signature using the configured secret
2. Filters to `pull_request` events only
3. Parses the payload into a `WebhookEvent` model
4. Enqueues with idempotency check (Redis `SET NX`)
5. Returns 200 immediately (fire-and-forget)

**Key design:** Fast acknowledgment. All processing happens asynchronously. GitHub retries webhooks if they don't get a 200 within ~10 seconds, so the receiver must be fast.

### 2. Event Queue (Phase 2)

**File:** `queue/event_queue.py`

Redis-backed FIFO queue with idempotency:

- **Deduplication:** `SET NX` with TTL on `delivery_id` prevents duplicate processing
- **FIFO ordering:** `RPUSH`/`BLPOP` for reliable message ordering
- **Processing markers:** Track in-flight events with TTL (10 min) to detect crashes

### 3. Context Assembly (Phase 3)

**File:** `context/assembly.py`, `context/github_client.py`, `context/smart_context.py`

Gathers everything the agents need:

1. **Fetches the diff** from GitHub API (raw diff + parsed file list)
2. **Smart context selection** — doesn't fetch every file in the repo, only:
   - Files imported by changed files
   - Sibling files in the same directory
   - Test files that import changed modules
3. **Language detection** — identifies file types for agent routing
4. **Repo metadata** — default branch, languages, recent commits

**Key design:** Context budget. We can't send the entire repo to the LLM. Smart selection keeps context under token limits while providing enough information for meaningful review.

### 4. LLM Client (Phases 6-9)

**File:** `context/llm_client.py`

Shared client used by all 4 agent nodes:

- Calls OpenAI API with retry logic (2 attempts)
- Parses JSON from LLM responses (handles markdown fences, partial JSON)
- Structured output format: `{ "findings": [...] }`
- Default model: `gpt-4o-mini` (cost-effective for code review)

### 5. LangGraph Pipeline (Phase 5)

**File:** `orchestrator/graph.py`, `orchestrator/nodes.py`, `orchestrator/state.py`

The core review pipeline, defined as a state graph:

```
context_assembly → [security, architecture, quality, documentation] → synthesis → HITL check
```

**Parallel execution:** LangGraph executes nodes with no dependency edges in parallel. All 4 agents run simultaneously.

**State management:** `ReviewState` TypedDict with `Annotated` reducers for fields written by multiple parallel nodes (e.g., `agent_results` dict is merged).

### 6. Agent Nodes (Phases 6-9)

Each agent follows the same pattern:

1. **System prompt** — defines the agent's role and what to look for
2. **User message** — contains repo info, PR metadata, and diff summary
3. **LLM call** — `call_llm()` with retry
4. **JSON parsing** — extract findings from response
5. **Graceful fallback** — returns empty findings on API failure

| Agent | Focus Areas | OWASP / Patterns |
|-------|-------------|------------------|
| Security | Injection, secrets, access control, SSRF | OWASP Top 10 A01-A10 |
| Architecture | Coupling, layering, module boundaries | SOLID, YAGNI, DI |
| Quality | Bugs, edge cases, performance | DRY, null safety, async |
| Documentation | README, docstrings, changelog | API doc conventions |

### 7. Synthesis (Phase 11)

**File:** `orchestrator/nodes.py` (synthesis_node)

Merges findings from all agents:

1. Collects all findings from all agent results
2. **Deduplicates** by `(file, line, category)` tuple
3. **Sorts by severity** (CRITICAL first)
4. **Applies cap** — configurable `max_comments_per_pr`
5. **HITL check** — if any finding has confidence < `HITL_CONFIDENCE_THRESHOLD`
   (default 0.7), escalate
6. **Merges cache hits** — findings reused from the Phase 14 cache are folded in
   alongside live agent findings
7. **Computes cost** from real prompt/completion token counts

### 8. Rate Limiting (Phase 17)

**File:** `rate_limiter.py`

Redis-based sliding window rate limiter:

- **Global:** N reviews per minute (prevents overload)
- **Per-repo:** N reviews per repo per hour (prevents spam)
- **Daily token budget:** checked *before* the LLM runs, then debited with the
  real token count afterwards — this is the enforced cost ceiling
- **Per-review cost:** advisory warning computed from real token usage

### 9. GitHub Posting (Phase 13)

**File:** `github/comment_poster.py`

Posts the review as a GitHub PR review:

- **Summary body** — formatted findings table + detailed breakdown
- **Inline comments** — per-line findings on the diff
- **Event selection** — `REQUEST_CHANGES` for critical/high, `COMMENT` otherwise, `APPROVE` for clean reviews
- **State tracking** — stores GitHub review ID for future reference

### 10. Database Schema (Phase 4)

**File:** `db/models.py`

8 tables in Postgres:

| Table | Purpose |
|-------|---------|
| `reviews` | PR review lifecycle (pending → completed → posted). One row per analyzed push. |
| `findings` | Individual findings from agents |
| `agent_results` | Per-agent output (tokens, confidence, duration) |
| `event_traces` | Time-series observability data |
| `feedback` | Developer thumbs up/down on findings |
| `code_embeddings` | Code embeddings for semantic search (JSON vectors) |
| `review_approvals` | HITL approval/rejection records |
| `file_cache` | Cached findings for unchanged files |

**Schema ownership:** Alembic owns the schema. `init_db()` only *verifies* that
`alembic upgrade head` has run — it deliberately does not call `create_all`,
which would leave a database with tables but no `alembic_version` row and
break later migrations.

### 11. Feedback Loop (Phase 16)

**File:** API endpoints in `webhooks/receiver.py`

- `POST /findings/{id}/feedback` — submit positive/negative feedback
- `GET /repos/{name}/feedback` — aggregated acceptance rate
- Updates `FindingRow.is_accepted` for analytics

### 12. Caching (Phase 14)

**File:** `db/repositories.py` (cache methods)

File-level caching:

- Hash content of each changed file
- Cache findings per (repo, file, agent_type)
- On PR update, skip re-analysis of unchanged files
- Track cache hit rate for monitoring

## Data Flow

### Webhook → Review Complete

```
1. GitHub sends webhook POST
2. HMAC verified, payload parsed, enqueued to Redis
3. Event processor dequeues (BLPOP)
4. Rate limit check (Redis counters)
5. Context assembled (GitHub API + smart selection)
6. Review record created in Postgres
7. LangGraph pipeline executes:
   a. Context assembly node validates
   b. 4 agents run in parallel (LLM calls)
   c. Synthesis deduplicates and sorts
   d. HITL check (low confidence → pause)
8. Results persisted to Postgres
9. If approved, findings posted to GitHub as PR review
10. Metrics recorded, event marked completed
```

### HITL Flow

```
1. Synthesis detects low-confidence findings
   (confidence < HITL_CONFIDENCE_THRESHOLD, default 0.7)
2. Review status → awaiting_approval
3. Processor returns (does not post to GitHub)
4. Developer reviews via POST /reviews/{id}/approve
5. If approved → posted to GitHub, status → completed
6. If rejected → nothing posted, status → skipped
7. If edited → edited findings JSON posted, status → completed
```

If the GitHub call fails during approval, the endpoint returns `502` and the
review remains `awaiting_approval` so the operator can retry. The approval is
only recorded once posting succeeds.

**Confidence threshold:** escalation is `confidence < threshold`, not `<=`,
and findings without a model-supplied confidence default to `0.8`. This keeps
the happy path viable — an earlier `confidence < 0.85` check combined with a
`0.7` parse default escalated essentially every review, so nothing ever posted.

## Error Handling

| Failure | Behavior |
|---------|----------|
| Webhook HMAC fails | Return 401, no processing |
| Duplicate delivery | Redis dedup returns False, return "duplicate" |
| Redis down | Log warning, continue (best-effort) |
| GitHub API fails | Return empty findings, log error |
| LLM API fails | Retry once, then return empty findings |
| LLM returns invalid JSON | Retry once, then return empty findings |
| Postgres down | Log error, event stays in queue |
| Rate limit exceeded | Skip processing, log warning, record trace |
| Daily token budget exceeded | Skip processing *before* any LLM spend |
| Per-review cost over cap | Log warning (advisory; the daily budget is the hard ceiling) |
| Context assembly fails | Review marked `failed`; agents and synthesis are skipped |
| GitHub posting fails | Log error; review stays `completed` without a review id (retry via HITL if escalated) |

## Scaling Considerations

**Current design handles:**
- ~30 reviews/minute global
- ~10 reviews/repo/hour
- Single-event processing (one worker)

**For higher scale:**
- Multiple event processors (consumer groups)
- Connection pooling tuning
- **pgvector index for semantic search** — embeddings are currently stored as
  JSON text and scored with cosine similarity in Python (`semantic_search`
  scans up to 500 rows per query). This is not yet a pgvector index.
- Read replicas for metrics queries
- LLM response caching (same diff → same findings)

## Security

- HMAC-SHA256 for webhook verification (prevent spoofing)
- Redis keys have TTL (prevent memory exhaustion)
- Rate limiting (prevent abuse)
- Cost caps (prevent runaway LLM spend)
- No secrets in logs (API keys redacted by structlog)
