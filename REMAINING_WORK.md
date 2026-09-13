# Remaining Work — PR Review Agent

**Document status:** handoff plan. Written 2026-09-12.
**Baseline:** Phases 1–18 and 20 implemented and wired. Phase 19 (multi-repo) deferred by design.

---

## 1. Where things actually stand

### 1.1 Verified working (with evidence)

| Area | Status | Evidence |
|---|---|---|
| Code quality gates | ✅ Green | `ruff check .` clean, `ruff format --check .` clean, `mypy src/pr_review_agent` clean |
| Test suite | ✅ Green | `116 passed, 0 skipped` (Redis + Postgres running) |
| Docker image build | ✅ Fixed | Image built successfully after Dockerfile fixes (see §3.1) |
| Full stack in Docker | ✅ Running | `pragent-app-1` (8000), `pragent-postgres-1` (5433→5432), `pragent-redis-1` (6379) all `healthy` |
| Schema migrations | ✅ In-container | 8 tables + `alembic_version`, stamped at head `002_review_history` |
| Re-review fix (unique index) | ✅ Live in DB | `ix_reviews_repo_pr` is `btree` **without** `UNIQUE` |
| HTTP surface | ✅ | `/health` → 200; `/metrics` → 200 with live DB + Redis data; OpenAPI lists 8 routes |
| HMAC enforcement | ✅ | `POST /webhook` with no signature → 401 |
| Worker consumes events | ✅ | Redis `MONITOR` showed `SET pr_review:processing:*` → global + repo rate-limit `INCRBY`/`EXPIRE` → daily-budget `GET` → `DEL` on completion (0.77 s end-to-end) |
| Pre-flight token budget | ✅ Executing | The `GET pr-review:budget:tokens:<repo>:<date>` in `MONITOR` is the Phase 17 budget check running before any LLM spend |

### 1.2 One item left mid-flight — application logs invisible in Docker

**Symptom:** after startup, the app's own structured logs never appear in `docker compose logs app`. Uvicorn access logs and the *startup* structlog lines do appear; anything logged later (e.g. by the event worker) does not.

**What was ruled out by experiment:**
- The worker code path definitely runs — Redis `MONITOR` proved `mark_processing`, the rate limiter, the budget check and `mark_completed` all executed for a synthetic event.
- Logging itself is not broken: running `configure_logging()` + `log.info(...)` inside the container printed correctly.
- Uvicorn's `dictConfig` does **not** strip the root handler or change the root level (verified in-container: root stayed at `20`/INFO with its stdout `StreamHandler`, and structlog still emitted before *and* after `dictConfig`).
- Therefore the fragility is structural: routing structlog through the stdlib **root** logger means any interaction that leaves root without a handler or above the configured level silently swallows every application log, while uvicorn's own loggers keep working.

**Change already applied (NOT yet verified in Docker):** `src/pr_review_agent/app.py` → `configure_logging()` now uses structlog's own `PrintLoggerFactory(file=sys.stdout)` with `make_filtering_bound_logger(level)`, so application logs no longer depend on the stdlib root logger at all. Stdlib logging is still configured for third-party/uvicorn loggers, with `httpx`/`httpcore`/`openai`/`urllib3` pinned to `WARNING`.

Local checks after the change: ruff clean, mypy clean, 116 passed.

**Acceptance criteria for closing this item:**
```bash
docker compose up -d --build app
docker compose exec -T redis redis-cli RPUSH pr-review:pending '{"id":"probe-final","type":"pr_opened","payload":{"action":"opened","number":999,"pull_request":{"number":999,"title":"probe","head":{"sha":"deadbeef"},"base":{"ref":"main"},"user":{"login":"probe"}},"repository":{"full_name":"probe-does-not-exist/repo"}}}'
docker compose logs app | grep -E "processing_event|event_processing_failed"
```
Both `processing_event` (INFO) and `event_processing_failed` (ERROR) lines must appear.

**If they still do not appear, next steps (in order):**
1. Add a regression test on the *real* pipeline, not the config: spin up `configure_logging()`, emit a log, assert it reached a captured stream — and add an equivalent test that runs **after** `logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)` so any future regression is caught by CI.
2. Compare against a foreground run to eliminate Docker log capture as a variable:
   `docker compose run --rm --service-ports app sh -c "python -m alembic upgrade head && python -m pr_review_agent.app"` and watch stdout live.
3. As a last resort, write to `sys.stderr` (unbuffered under uvicorn) and confirm.

**Related, also applied but unverified in Docker:** version single-sourcing. `pr_review_agent/__init__.py` now defines `__version__ = "0.3.0"`, and both the FastAPI app and the `/metrics` payload read it. The running container still reports `0.2.0` until rebuilt.

---

## 2. Remaining engineering work

Effort: **S** ≤ 1 hour · **M** ≈ half a day · **L** ≈ multi-day.

### P0 — Integration tests against real infrastructure — **(M)** — highest value

**Why:** `tests/conftest.py` defines `db_engine` and `db_session` fixtures that **nothing uses**, so there are currently **zero tests touching a real Postgres**. Critically, the re-review fix is only asserted at the *schema* level (index uniqueness) — nothing proves that creating a second review for the same PR actually succeeds. The same is true for caching, approvals, and the budget cap.

**Deliverables:**
- `create_review` twice for the same `(repo, PR)` both persist, with distinct ids (behavioural proof of the `002_review_history` fix).
- Cache round-trip: first run caches findings; second run with an unchanged patch reuses them and **`call_llm` is never invoked** (assert via monkeypatch counter).
- Approval flow against a real DB row: status transitions and `github_pr_review_id` persistence.
- Daily token budget: `record_token_spend` to the limit, then assert the next event is skipped **before** any LLM call.
- Duplicate `delivery_id` yields one queued event.
- Traces: `event_traces` rows are actually written for a processed event.

**Also:** make CI run them on every PR. Today the `integration` job only fires on push to `main`, and the tests skip when services are absent. Either add the services to the default `test` job or gate the integration tests on a marker (e.g. `-m integration`) and run that job on pull requests too.

**Acceptance:** with Postgres + Redis up, `pytest` runs these with **0 skips** and fails if any behaviour regresses.

### P1 — Event reliability: retry + dead-letter — **(M)**

**Why:** failures are **dropped**. Both `except` branches in `EventProcessor._process_event` call `queue.mark_completed`, so a transient GitHub/OpenAI/Postgres outage loses the review permanently with no retry and no record.

**Deliverables:** attempt counter in Redis; bounded retries with exponential backoff and jitter; after N attempts, move the payload to a dead-letter list with the failure reason, emit a trace, and expose `dead_letter_count` in `/metrics`. Never mark a failed event completed.

**Watch out:** retries must be idempotent — the Phase 14 cache and the review row creation both need to tolerate a repeat run for the same `delivery_id`.

### P2 — API authentication — **(S)** — security

**Why:** **no route has any authentication.** Anyone able to reach the server can `POST /reviews/{id}/approve` and post a review to GitHub as your bot — bypassing the HITL gate entirely — and can read `/metrics`, `/reviews/{id}`, and `/repos/{name}/*`.

**Deliverables:** an admin/shared-secret dependency guarding all non-webhook routes (`/health` may stay open for the healthcheck). Constant-time comparison. Document the header. Keep `/webhook` on HMAC only.

**Note:** the Docker healthcheck calls `/health`, so that endpoint must remain unauthenticated.

### P3 — Log redaction — **(S)**

**Why:** `ARCHITECTURE.md` claims *"No secrets in logs (API keys redacted by structlog)"*. **This is false** — there is no redaction processor, and OpenAI/GitHub exception strings can echo credentials.

**Deliverables:** either a structlog processor that masks values matching the configured `OPENAI_API_KEY` / `GITHUB_TOKEN` / `GITHUB_WEBHOOK_SECRET`, or correct the claim. Implementing is preferred. Add a test asserting a known secret never appears in rendered output.

### P4 — Feedback endpoint validation — **(S)**

`POST /findings/{id}/feedback` with an unknown id currently raises an `IntegrityError` → **500**. Should be a clean `404`.

### P5 — Operations runbook — **(S)**

Deploy/rollback (`alembic downgrade`), what to watch on `/metrics` (`reviews_last_24h`, `findings_by_severity`, `avg_confidence`, queue depth, rate-limit usage), how to interpret a stuck `awaiting_approval` backlog, how to replay a dead-lettered event, and the log lines that indicate each failure mode.

### P6 — pgvector upgrade — **(L)** — only at scale

Semantic search stores embeddings as JSON text and scores with cosine similarity in Python, scanning up to 500 rows per query (`ReviewRepository.semantic_search`). Fine for small/medium repos; a real `vector(1536)` column with an HNSW/ivfflat index is the documented upgrade path. Requires a data migration and a new dependency.

### P7 — Concurrency and scale — **(L)** — only at load

Single processor, no consumer groups, no LLM response cache. `/metrics` also creates a **new Redis client per request**. Defer until volume justifies it.

### P8 — Phase 19: multi-repo / monorepo support — **(L)** — deferred by design

---

## 3. Fixes already made in this session (for context)

### 3.1 Docker / deployment
- `Dockerfile`: `COPY src/ src/` added to the **builder** stage — `pip install .` with only `pyproject.toml` present cannot build the wheel (the backend needs the package directory).
- `Dockerfile`: entrypoint uses `python -m alembic` instead of the bare `alembic` console script, so it does not depend on `PATH` inside the image.
- `pyproject.toml`: `alembic` moved from the `dev` extra into **runtime** dependencies, because the container entrypoint runs `python -m alembic upgrade head` before serving. Previously the image had no Alembic at all and the container would exit immediately.
- `docker-compose.yml`: removed the obsolete `version:` attribute; Postgres now publishes **`5433:5432`**; added `DATABASE_URL_SYNC` so both URLs are overridden consistently inside the compose network.
- `.gitignore` created (there was none) — `.env`, caches, build output.

### 3.2 Database / migrations
- `migrations/versions/002_review_history.py`: drops the **unique** `(repo, PR)` index and recreates it non-unique. Without this, the second `synchronize` webhook for a PR raised `IntegrityError` and the review was silently dropped.
- `migrations/env.py`: resolves the DB URL through application `settings` (honours `env vars > .env > default`) instead of reading only `os.environ`. Alembic and the app can no longer target different databases. Also normalises sync → `postgresql+asyncpg` for the async engine, which is what the CI integration job needs.
- `alembic.ini`: `sqlalchemy.url` removed so it cannot silently override settings.
- `db/connection.py`: `init_db()` now only **verifies** that migrations have run; it no longer calls `create_all`. Creating tables outside Alembic left databases with tables but no `alembic_version` row, which later migrations reject.
- `db/models.py`: `ix_reviews_repo_pr` is non-unique, matching migration `002`.

### 3.3 Pipeline correctness
- **HITL threshold:** escalation moved behind `HITL_CONFIDENCE_THRESHOLD` (default `0.7`). Previously `confidence < 0.85` combined with a `0.7` parse default escalated essentially every review, so Phase 13 never posted anything.
- **Approval actually posts:** `POST /reviews/{id}/approve` records the approval *and* posts to GitHub, supports `approved`/`rejected`/`edited`, honours `edited_findings_json`, and returns `502` leaving the review `awaiting_approval` when posting fails.
- **Real token/cost accounting:** `call_llm` returns an `LLMCallResult` with real `prompt_tokens`/`completion_tokens`; cost is computed from configured per-1M pricing. Previously `findings × 150` and a hardcoded rate.
- **Pre-flight budget:** per-repo daily token budget checked before any LLM spend, then debited with actual usage.
- **Failed context assembly no longer "completes":** agents skip their LLM calls and synthesis preserves `FAILED` instead of overwriting it with `COMPLETED`.
- **Phase 14 cache wired:** unchanged files reuse cached findings; if every file is a cache hit the pipeline skips the LLM entirely.
- **Phase 16 feedback wired:** findings marked thumbs-down surface as prompt guidance so the agents avoid repeating false positives.
- **Phase 18 traces wired:** `record_trace` is called at the pipeline's key points.
- **Phase 10 wired:** semantic-search enrichment in context assembly plus `pr-review-agent index owner/repo`; previously `EmbeddingService` had no callers.
- **Redis robustness:** `EventQueue.connect()` no longer stores a dead client on a failed `ping()`, and the processor refuses to start with a clear error instead of crashing on first dequeue.

### 3.4 Test isolation
- `tests/conftest.py`: an autouse fixture clears `github_webhook_secret` / `github_token` / `openai_api_key` so tests no longer depend on the developer's `.env`. Redis/Postgres fixtures **skip** (not error) when services are unreachable.
- `tests/test_webhook_receiver.py`: rewritten to configure a secret and sign payloads, plus new coverage for 401 on a missing signature, duplicate deliveries, and dev-mode skip.
- New test files: `test_synthesis_and_cost.py`, `test_llm_client.py`, `test_approval_flow.py`, `test_cached_review.py`, `test_cli.py`, `test_migrations.py`.

---

## 4. Manual steps (yours — I cannot do these)

### 4.1 Done already
- ✅ Docker Desktop installed and running; `redis` and `postgres` containers healthy.
- ✅ Dev dependencies installed (`pip install -e ".[dev]"`) — Alembic 1.20.0 present, package installed editable.
- ✅ Schema created and stamped at head — done automatically by the container entrypoint.

### 4.2 Outstanding

**M1 — Real credentials in `.env`** *(blocking any live review)*
Set genuine values for `OPENAI_API_KEY`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`.
`GITHUB_TOKEN` needs `pull_requests: write` and `contents: read`.
Also decide: `GITHUB_COMMENT_MODE` (`summary` \| `inline` \| `both`) and `HITL_CONFIDENCE_THRESHOLD`.

**M2 — GitHub webhook registration** *(blocking webhook-driven reviews)*
Settings → Webhooks → Add webhook:
- Payload URL: `https://<your-host>/webhook`
- Content type: `application/json`
- Secret: the same value as `GITHUB_WEBHOOK_SECRET`
- Events: **Pull requests** only

**M3 — Public URL for local Docker** *(blocking M2)*
GitHub cannot reach `localhost:8000`. Expose it, e.g. `ngrok http 8000`, and use the tunnel URL in M2.

**M4 — `.env` database port** *(only needed for host-side runs)*
For **Docker-only** usage this does **not** matter: compose injects `postgres:5432` into the app container, overriding `.env`. It matters only if you run migrations or the app from the host, where `.env` still says `5432` → which is your **native PostgreSQL 18**, not the container. Change both lines to `5433`:
```
DATABASE_URL=postgresql+asyncpg://pr_agent:pr_agent_secret@localhost:5433/pr_review_agent
DATABASE_URL_SYNC=postgresql://pr_agent:pr_agent_secret@localhost:5433/pr_review_agent
```

**M5 — `PATH` for the console scripts** *(quality of life)*
`alembic.exe` and `pr-review-agent.exe` live in
`C:\Users\pavne\AppData\Roaming\Python\Python312\Scripts`, which is not on `PATH`.
Either add that folder to `PATH`, or always use the module form:
```bash
python -m alembic upgrade head
python -m pr_review_agent.cli serve
```

**M6 — Optional: index a repo for semantic context**
```bash
python -m pr_review_agent.cli index owner/repo
```
Without this, semantic search logs `semantic_search_skipped` and only the heuristic context selection is used.

**M7 — Git hygiene**
This directory is **not a git repository**. There was also no `.gitignore` until this session, and `.env` holds real credentials. Before initialising git, confirm `.env` is ignored, and if those keys were ever pushed anywhere, rotate `OPENAI_API_KEY` and `GITHUB_TOKEN`.

**M8 — Decide on the port conflict long-term**
Your native `postgresql-x64-18` still owns 5432 while the container is on 5433. If you ever stop using the container, remember the app expects 5433 (or set `DATABASE_URL` accordingly). Optional: `sc config postgresql-x64-18 start= demand` to stop it auto-starting.

---

## 5. Suggested order

| Step | Owner | Item | Why now |
|---|---|---|---|
| 1 | me | **Close §1.2** (verify logging fix in Docker) | Blocks any useful operation — you currently cannot see what the pipeline is doing |
| 2 | you | **M1, M3, M2** | Nothing end-to-end can happen without credentials and a reachable webhook |
| 3 | me | **P0** integration tests + CI wiring | The only real proof the fixes hold; guards every later change |
| 4 | me | **P2, P3, P4** | Small, security/robustness focused; batch together |
| 5 | me | **P1** retry + dead-letter | Do before pointing at repos you care about |
| 6 | me | **P5** runbook | Needed once others are operating it |
| 7 | later | **P6, P7, P8** | Only when scale or requirements demand |

---

## 6. Definition of done — first live review

A real PR produces a real GitHub review:

1. `docker compose ps` → `app`, `postgres`, `redis` all `healthy`.
2. `docker compose logs app` shows `database_ready` and `connected_to_redis`.
3. Open a test PR → GitHub webhook delivery shows `200 {"status":"queued"}`.
4. `docker compose logs app` shows `processing_event`, `context_assembled`, `review_completed`.
5. `curl -s localhost:8000/metrics` shows `total_reviews` incremented.
6. The review appears on the PR.

If findings are low-confidence the review stops at `awaiting_approval` (correct behaviour) — approve it to post:
```bash
curl -X POST localhost:8000/reviews/<id>/approve \
  -H 'Content-Type: application/json' \
  -d '{"approver":"you","decision":"approved"}'
```
(Note: this endpoint is currently unauthenticated — see **P2**.)
