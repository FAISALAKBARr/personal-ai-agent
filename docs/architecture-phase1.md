# Personal AI Agent (WhatsApp) — Phase 1 Architecture

Reference doc derived from the Master Prompt V2 specification. Covers Phase 1 ("Core") only — later phases build on this foundation without requiring a redesign.

## 1. Design principles carried into Phase 1
- Local-first, provider-independent AI (Ollama default; Claude/OpenAI optional via a provider interface)
- Deterministic, non-LLM permission enforcement (Capability Firewall)
- Human-in-the-loop for anything CONFIRM-tier
- Full audit trail for every tool execution, including blocked attempts
- Idempotent message and job handling
- Single-user assumption (one allowlisted WhatsApp number) — see §12

## 2. Phase 1 request lifecycle
```
WhatsApp message
  -> Gateway adapter (Cloud API or Baileys) normalizes to InboundMessage
  -> FastAPI webhook (/messages) — verifies signature, checks phone allowlist
  -> Orchestrator
       1. Intent classification (subset: INFORMATION / SIMPLE_ACTION / MULTI_STEP_ACTION)
       2. Minimal plan (1-3 steps)
       3. Tool request
  -> Capability Firewall
       - ALLOW   -> execute immediately
       - CONFIRM -> create Approval, ask user, wait (expires if no response)
       - BLOCK   -> refuse, log, explain — never reaches a tool
  -> Tool execution (create_task / get_tasks / update_task / create_reminder)
  -> Verification (did the write actually succeed / does the read match expectations)
  -> Audit log entry (every branch, including BLOCK)
  -> WhatsApp response
```

## 3. Orchestrator: custom state machine, not LangGraph (yet)
For Phase 1 the state space is small enough that a plain async Python state machine is simpler to reason about, test, and debug than adopting LangGraph immediately. Revisit LangGraph once Phase 4/5 introduces real branching, parallel tool calls, and long-running multi-agent plans.

States: `RECEIVED -> CLASSIFIED -> PLANNED -> (AWAITING_APPROVAL) -> EXECUTING -> VERIFIED -> RESPONDED -> (FAILED)`

## 4. Capability Firewall
A permission evaluator that is never an LLM call:

```python
def evaluate(tool_name: str, params: dict, user_id: str) -> Decision:
    policy = POLICY_TABLE[tool_name]  # loaded from config, not the prompt
    if policy.level == "BLOCKED":
        return Decision.BLOCK
    if policy.level == "CONFIRM":
        return Decision.CONFIRM
    return Decision.ALLOW
```

Phase 1 policy table:

| Tool | Level |
|---|---|
| get_tasks | SAFE |
| create_task | SAFE |
| update_task | SAFE |
| create_reminder | SAFE |
| (placeholder) delete_task | CONFIRM |

The LLM only ever produces a *requested* tool call; this table is the sole source of truth for what actually runs. It ships as a YAML file for Phase 1 (easy to review/diff in git); move it to a DB table once you want to edit policy from the dashboard in Phase 7.

## 5. Identity & webhook security
- Single-user for Phase 1: one allowlisted WhatsApp number maps to one `users` row.
- Every inbound webhook is signature-verified (HMAC with the app/webhook secret) before any processing — reject anything that doesn't verify.
- `messages.whatsapp_message_id` has a unique constraint, so a duplicated webhook delivery is a no-op, not a duplicate action.

## 6. Scheduler (pulled forward from Phase 2)
Definition of Done #1 (§45 of the spec) requires a reminder that fires at the correct time and survives a restart — that needs a persistent scheduler, not an in-memory timer, even though the spec's own phase list (§43) puts "scheduler" in Phase 2. Phase 1 uses **APScheduler with a SQLAlchemy jobstore** (jobs persisted in Postgres). Simpler to operate than Celery + beat for a single-user system; revisit Celery only if this grows multi-worker.

## 7. Kill switch (minimal version, pulled forward)
A single row (`system_state.paused = true/false`) checked at the top of the orchestrator and the scheduler tick. Cheap to add now, safety-critical, and non-negotiable per §46 of the spec — no reason to defer it.

## 8. WhatsApp gateway: Cloud API vs Baileys
The biggest open decision, and the trade-off has shifted recently:

**WhatsApp Cloud API (official, Meta)**
- Since July 1, 2025, Meta bills per message sent rather than per 24-hour conversation window.
- Non-template "service" replies (free-form messages within the customer-service window) had been free since November 2024 — but starting **October 1, 2026**, service and utility messages sent inside that 24-hour window start costing money again. That's the message type a personal assistant mostly sends, so Cloud API stops being effectively free for this use case very soon.
- Rough mid-2026 US rate card: marketing templates ~$0.025/message, utility/authentication ~$0.004/message (varies by country/category).
- Going through a third-party BSP instead of Meta directly typically adds ~$0.003–$0.010/message markup on top.
- Requires Meta Business verification, a registered phone number, and a public HTTPS webhook endpoint (ngrok/Cloudflare Tunnel for local dev).

**Baileys (unofficial, open-source)**
- Actively maintained (WhiskeySockets/Baileys, ~9,600 GitHub stars), speaks the WhatsApp Web multi-device protocol directly over WebSocket — no headless browser needed.
- Free — doesn't touch Meta's billing system at all.
- Unofficial: the maintainers explicitly state they don't condone ToS-violating use, and running an automated client this way carries a real risk of the number getting banned, especially under heavy traffic.
- Just shipped v7 with breaking changes — follow the current migration guide if starting fresh.
- Node.js-only, so it needs a small companion service (an extra runtime + an internal REST/WS bridge to FastAPI) rather than being called directly from Python.

## 9. Dependencies (Phase 1)

**Python / backend**
- fastapi, uvicorn[standard]
- pydantic v2, pydantic-settings
- sqlalchemy[asyncio] 2.x, asyncpg, alembic
- redis (redis-py)
- apscheduler (SQLAlchemy jobstore)
- httpx
- ollama (python client) or raw HTTP to a local Ollama server
- pytest, pytest-asyncio

**Infra**
- Docker, Docker Compose
- Postgres — use the `pgvector/pgvector` image now even though pgvector isn't used until Phase 3, to avoid a migration later
- redis:7
- Ollama — runs **natively on the host**, not as a Compose service. Decided after testing on Windows + NVIDIA GPU: containerized GPU passthrough needs the NVIDIA Container Toolkit configured for WSL2, which buys nothing over a native install that already has GPU access. Backend reaches it via `host.docker.internal`. This trade-off flips on Linux, where container GPU passthrough is simpler — see the commented-out service in `docker-compose.yml` if deploying there.

**WhatsApp gateway (one of, TBD — see §8)**
- Cloud API: just `httpx` + a public HTTPS endpoint
- Baileys: an additional Node.js service in Compose

## 10. Repo structure (Phase 1 slice)
```
personal-ai-agent/
├── backend/
│   ├── app/
│   │   ├── api/            # routers: messages, tasks, approvals, health
│   │   ├── agents/         # orchestrator, intent classifier, minimal planner
│   │   ├── auth/           # phone allowlist, webhook signature verification
│   │   ├── core/           # settings (pydantic-settings), logging
│   │   ├── database/       # engine/session, Alembic migrations
│   │   ├── memory/         # Phase 1: plain text facts, no embeddings yet
│   │   ├── permissions/    # Capability Firewall + policy table
│   │   ├── approvals/      # Approval Engine
│   │   ├── tools/          # create_task, get_tasks, update_task, create_reminder
│   │   ├── scheduler/      # APScheduler wrapper
│   │   ├── whatsapp/       # Gateway interface + one adapter
│   │   ├── models/         # SQLAlchemy ORM
│   │   └── schemas/        # Pydantic I/O schemas
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── infra/
│   ├── docker-compose.yml  # backend, postgres, redis, ollama (+ node bridge if Baileys)
│   └── configs/
├── docs/
│   └── architecture.md     # this file
├── .env.example
└── README.md
```
Everything else in the spec's original §42 structure (frontend/, browser agent, career/developer agents, n8n, MinIO) is deliberately absent from Phase 1 — added in later phases per the spec's own roadmap.

## 11. Database schema (Phase 1)

| Table | Purpose | Key columns |
|---|---|---|
| users | one row per allowlisted person | id, whatsapp_number (unique), display_name, created_at |
| conversations | groups messages | id, user_id, started_at, last_message_at |
| messages | every inbound/outbound message | id, conversation_id, whatsapp_message_id (unique), direction, content, message_type, created_at |
| tasks | reminders / todos | id, user_id, title, description, due_at, status, priority, created_at, updated_at |
| scheduled_jobs | durable schedule for tasks | id, task_id, job_type, run_at, cron_expression, status, last_fired_at |
| approvals | pending/resolved CONFIRM actions | id, user_id, action, target, parameters (JSONB), status, expires_at, created_at, resolved_at |
| audit_logs | every tool execution | id, user_id, agent_run_id, tool_name, parameters (JSONB, redacted), permission_decision, result, error, duration_ms, created_at |
| agent_runs | one row per user request | id, user_id, conversation_id, goal, status, plan (JSONB), current_step, created_at, completed_at |
| memories | explicit/inferred facts | id, user_id, category, content, source (explicit/inferred), confidence, created_at |
| system_state | kill switch + global flags | key, value, updated_at |

## 12. Concrete Phase 1 "done" checklist
- [ ] "Remind me tomorrow at 8 AM to work on my portfolio" -> task + scheduled_job created, confirmation sent, reminder fires at the correct time, survives a container restart
- [ ] "What are my tasks?" -> SAFE tool runs automatically, list returned
- [ ] A CONFIRM-tier action asks for approval; only the exact approved action executes, and it's recorded in `approvals` + `audit_logs`
- [ ] Every tool execution appears in `audit_logs` with secrets redacted
- [ ] A duplicated WhatsApp webhook delivery does not create a duplicate task or send a duplicate reply
- [ ] "STOP" / "PAUSE AGENT" halts pending agent actions immediately

## 13. Open decisions
1. WhatsApp gateway: Cloud API vs Baileys (§8)
2. Where this runs + hardware available for Ollama (affects model choice)
3. Confirm: single-user scope for Phase 1 (assumed above — flag if wrong)
