# Agent Memory Server

> A production-oriented, multi-tenant memory plane for AI agents that models **working, episodic, semantic, and procedural memory as different data products** rather than treating agent memory as a single vector database.

**Version:** 1.0.0  
**Runtime:** Python 3.11+ / FastAPI / PostgreSQL / pgvector / Redis  
**Primary use:** durable cross-run memory for autonomous agents, copilots, multi-agent systems, LangGraph applications, and Muse-style persistent agents.

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Why an agent memory server exists](#2-why-an-agent-memory-server-exists)
3. [Memory taxonomy](#3-memory-taxonomy)
4. [Architecture](#4-architecture)
5. [End-to-end request flows](#5-end-to-end-request-flows)
6. [Repository structure](#6-repository-structure)
7. [Code walkthrough](#7-code-walkthrough)
8. [Data model and storage design](#8-data-model-and-storage-design)
9. [Retrieval and ranking](#9-retrieval-and-ranking)
10. [Memory lifecycle and consolidation](#10-memory-lifecycle-and-consolidation)
11. [API reference](#11-api-reference)
12. [Quick start with Docker Compose](#12-quick-start-with-docker-compose)
13. [Run locally without Docker for the API](#13-run-locally-without-docker-for-the-api)
14. [Testing](#14-testing)
15. [Configuration](#15-configuration)
16. [Application integration patterns](#16-application-integration-patterns)
17. [LangGraph integration](#17-langgraph-integration)
18. [Meta Muse-style integration](#18-meta-muse-style-integration)
19. [Security and governance](#19-security-and-governance)
20. [Reliability and consistency](#20-reliability-and-consistency)
21. [Observability and SLOs](#21-observability-and-slos)
22. [Performance and capacity planning](#22-performance-and-capacity-planning)
23. [Scaling architecture](#23-scaling-architecture)
24. [Deployment to Kubernetes](#24-deployment-to-kubernetes)
25. [Failure modes and recovery](#25-failure-modes-and-recovery)
26. [Privacy, retention, and deletion](#26-privacy-retention-and-deletion)
27. [Production hardening checklist](#27-production-hardening-checklist)
28. [Design trade-offs](#28-design-trade-offs)
29. [Interview / Principal Engineer discussion guide](#29-interview--principal-engineer-discussion-guide)
30. [Troubleshooting](#30-troubleshooting)
31. [Roadmap](#31-roadmap)
32. [License](#32-license)

---

## 1. Executive summary

Large language models are stateless between calls unless an application supplies state. A serious agent therefore needs more than conversation history. It needs a memory subsystem capable of answering four different questions:

| Memory class | Question | Typical data | Storage in this project |
|---|---|---|---|
| **Working** | What am I doing right now? | current goal, scratch state, temporary observations | Redis + TTL |
| **Episodic** | What happened before? | runs, incidents, interactions, outcomes | PostgreSQL + pgvector |
| **Semantic** | What do I know? | facts, concepts, preferences, entity knowledge | PostgreSQL + pgvector |
| **Procedural** | How have I successfully done this? | plans, workflows, tool sequences, constraints | PostgreSQL + pgvector |

The service exposes a small HTTP contract while keeping storage and retrieval behind adapters. The current repository is intentionally runnable on a laptop: PostgreSQL/pgvector and Redis start through Docker Compose, and the API uses a deterministic local embedding fallback so no external model account is required.

The **fallback embedding is for execution/testing only**. It is not a semantic model. A production deployment should replace `EmbeddingService` with a real embedding provider or locally hosted model and evaluate retrieval quality before launch.

### Core design principles

1. **Memory type is a semantic contract, not a tag.** Different memory classes have different retention, ranking, mutation, and governance rules.
2. **PostgreSQL is the durable source of truth.** The ANN index is an access path, not authoritative state.
3. **Working state is disposable/reconstructable.** Do not promote every scratch observation into durable knowledge.
4. **Retrieval is security-sensitive.** Tenant/agent/namespace constraints are applied in the query path.
5. **Provenance matters.** Model-generated claims should not silently become authoritative semantic facts.
6. **Memory is a lifecycle.** Acquisition, consolidation, contradiction resolution, retrieval, decay, retention, and deletion all matter.
7. **Checkpointing and memory are different.** Workflow checkpoints restore execution; memory transfers useful knowledge across executions.

---

## 2. Why an agent memory server exists

A naive agent commonly starts with this pattern:

```text
messages[] -> LLM -> response
```

As the interaction grows, developers append all prior messages. This eventually causes four problems:

- context windows are finite;
- irrelevant history increases token cost and latency;
- old or conflicting information distracts the model;
- history tied to one conversation does not automatically become reusable knowledge.

A memory plane introduces an explicit lifecycle:

```text
interaction
    |
    v
capture candidate memory
    |
    +--> working memory ------------------+
    |                                     |
    +--> durable episode                  |
              |                           |
              v                           |
       consolidation workers              |
        /             \                   |
       v               v                  |
 semantic facts    procedures             |
       \               /                  |
        +------ retrieval <---------------+
                  |
                  v
             ranked context
                  |
                  v
                 LLM
```

This makes memory independently governable, observable, scalable, and reusable by many agents.

### What this service is

- a dedicated memory API;
- a durable memory source of truth;
- a low-latency working-memory store;
- a vector retrieval layer;
- a clean boundary for adding lexical retrieval, reranking, consolidation, ACLs, retention, and auditing.

### What this service is not

- a replacement for the LLM context window;
- a workflow scheduler;
- a LangGraph checkpointer;
- a complete knowledge graph;
- a model-training system;
- a guarantee that retrieved text is true;
- a claim that the included single-region Compose stack is globally distributed infrastructure.

---

## 3. Memory taxonomy

### 3.1 Working memory

Working memory is short-lived state required to execute the current task.

Examples:

```text
current objective = "diagnose checkout latency"
active incident = "INC-218"
current plan step = 4
observed service = "payments-api"
partial SQL query = "SELECT ..."
```

Properties:

- low latency;
- session/run oriented;
- TTL based;
- frequently updated;
- normally reconstructable;
- should not automatically become durable truth.

This repository stores it in Redis using keys scoped by tenant, agent, namespace, and memory ID.

### 3.2 Episodic memory

Episodic memory records **events and experiences**.

Examples:

```text
"Deployment 42 failed because the DB migration ran after the application rollout."
"The user rejected recommendation A and selected B."
"Tool call to inventory-service timed out three times during run-92."
```

A richer production episode normally contains:

```text
run_id
session_id
occurred_at
actors
observation
action
outcome
reward/success
causal links
source/provenance
```

Episodic ranking often combines semantic relevance, recency, importance, and outcome.

### 3.3 Semantic memory

Semantic memory stores durable facts or concepts abstracted from observations.

Examples:

```text
"Service payments-api owns card authorization."
"Customer ACME requires EU data residency."
"Repository X deploys through workflow Y."
```

Production semantic memory should add:

- provenance;
- source authority;
- confidence;
- `valid_from` / `valid_until`;
- entity IDs;
- contradiction/supersession relationships;
- verification status.

**Important:** an LLM saying something does not make it a fact. Semantic promotion needs policy.

### 3.4 Procedural memory

Procedural memory stores reusable **methods**.

Examples:

```text
When deployment health fails:
1. query rollout status
2. inspect error-rate delta
3. compare schema version
4. rollback only if policy permits
```

A mature procedure record should contain:

```text
procedure_version
preconditions
ordered steps
tool/API schema versions
required permissions
postconditions
success_count
failure_count
last_success_at
approval status
```

Procedural memory is executable knowledge. Govern it more like code than like chat history.

### 3.5 Memory versus cache versus checkpoint

| Concept | Purpose | Example |
|---|---|---|
| Cache | avoid recomputation | cached embedding |
| Working memory | temporary reasoning/task state | active plan |
| Checkpoint | restore exact workflow execution state | LangGraph state snapshot |
| Long-term memory | transfer useful information across runs | preference/fact/episode/procedure |
| Audit log | immutable evidence of what changed | memory deletion event |

Do not collapse these abstractions into one database table just because they all persist bytes.

---

## 4. Architecture

### 4.1 Current runnable architecture

```text
                         +----------------------+
                         | Agent / Application  |
                         | Muse / LangGraph     |
                         +----------+-----------+
                                    |
                                    | HTTP/JSON
                                    v
                         +----------------------+
                         |      FastAPI API     |
                         | auth + validation    |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |    MemoryService     |
                         | routing + ranking    |
                         +-----+-----------+----+
                               |           |
                    working    |           | durable
                               v           v
                      +-------------+   +------------------+
                      |    Redis    |   |   PostgreSQL     |
                      | TTL memory  |   | + pgvector       |
                      +-------------+   +--------+---------+
                                                |
                                                v
                                      +--------------------+
                                      | HNSW cosine index  |
                                      +--------------------+
```

### 4.2 Target large-scale architecture

```text
                                  Clients / Agents
                                         |
                               API Gateway / WAF
                                         |
                                  Identity / OIDC
                                         |
                          +--------------v---------------+
                          |        Memory API Cell       |
                          | validation / authz / quotas  |
                          +---+----------------------+----+
                              |                      |
                       write path                recall path
                              |                      |
                  +-----------v--------+     +-------v----------------+
                  | Memory command svc |     | Retrieval orchestrator |
                  +-----+---------+----+     +---+---------+----------+
                        |         |              |         |
                  +-----v--+ +----v------+   +---v---+ +---v---------+
                  | Redis  | | Postgres  |   | FTS   | | Vector ANN  |
                  | WM     | | SoT       |   |       | |             |
                  +--------+ +----+------+   +---+---+ +------+------+
                                  |              \          /
                                  |               \        /
                           transactional           v      v
                              outbox          candidate fusion
                                  |                  |
                                  v                  v
                          +---------------+      reranker
                          | event stream  |          |
                          +---+-------+---+          v
                              |       |       policy + budgeter
                   +----------+       +----------+   |
                   v                             v   v
          consolidation workers          derived indexes/context
                   |
        +----------+-----------+
        |                      |
        v                      v
 semantic extraction     procedure learning
```

At scale, prefer **cell architecture**: each cell owns a bounded set of tenants/regions and contains its own API capacity, Redis, PostgreSQL shard/cluster, and workers. This limits blast radius and supports residency requirements.

---

## 5. End-to-end request flows

### 5.1 Remember working memory

```text
POST /v1/memories kind=working
       |
       v
Pydantic validation
       |
       v
MemoryService.remember()
       |
       v
WorkingMemoryRepository.put()
       |
       v
SET wm:<tenant>:<agent>:<namespace>:<uuid> EX <ttl>
```

No vector is required. The record expires automatically.

### 5.2 Remember durable memory

```text
POST /v1/memories kind=episodic|semantic|procedural
       |
       v
MemoryService.remember()
       |
       +--> EmbeddingService.embed(content)
       |
       v
PostgresMemoryRepository.put()
       |
       v
transactional INSERT / idempotent conflict handling
       |
       v
memories table + pgvector embedding
```

### 5.3 Recall

```text
POST /v1/recall
       |
       v
MemoryService.recall()
       |
       +---- if working requested ----> Redis scan + lexical overlap
       |
       +---- durable kinds -----------> embed query
                                          |
                                          v
                                   pgvector cosine ANN
                                          |
                                          v
                              similarity + importance blend
                                          |
                           merge / sort / top N response
```

The current ranker is intentionally understandable. Section 9 describes the production evolution.

### 5.4 Delete

```text
DELETE /v1/memories/<id>?tenant_id=<tenant>
       |
       v
UPDATE memories SET deleted_at = now()
```

This is a **soft tombstone** for durable memories. Full privacy erasure requires an asynchronous deletion lifecycle across replicas, backups, caches, derived stores, logs, and analytics.

---

## 6. Repository structure

```text
agent-memory-server/
|
+-- app/
|   +-- api/
|   |   +-- routes.py              # HTTP endpoints + development API-key auth
|   +-- core/
|   |   +-- config.py              # environment configuration
|   |   +-- db.py                  # async SQLAlchemy engine/session pool
|   +-- domain/
|   |   +-- models.py              # Pydantic domain/API models + MemoryKind
|   +-- repositories/
|   |   +-- postgres.py            # durable persistence + vector recall
|   |   +-- working.py             # Redis TTL working memory
|   +-- services/
|   |   +-- embedding.py           # deterministic local embedding adapter
|   |   +-- memory.py              # orchestration + routing + ranking
|   +-- workers/                    # extension point for async consolidation
|   +-- main.py                     # FastAPI application entry point
|
+-- migrations/
|   +-- 001_init.sql               # pgvector extension, schema, HNSW indexes
|
+-- tests/
|   +-- test_models.py             # model-level unit test starter
|
+-- k8s/
|   +-- deployment.yaml            # API Deployment baseline
|
+-- .env.example                   # configuration example
+-- docker-compose.yml             # local Postgres/pgvector + Redis + API
+-- Dockerfile                     # API image
+-- Makefile                       # convenience commands
+-- pyproject.toml                 # Python dependencies / project metadata
+-- README.md                      # this document
```

---

## 7. Code walkthrough

### `app/main.py`

Creates the FastAPI application and mounts the router.

```python
app=FastAPI(title='Agent Memory Server',version='1.0.0')
app.include_router(router)
```

Keep the entry point intentionally thin. Lifecycle hooks, telemetry initialization, and dependency wiring can be added here in a larger deployment.

### `app/domain/models.py`

Defines the public memory vocabulary.

`MemoryKind` prevents arbitrary memory classes. `MemoryWrite` validates incoming writes, including a 100,000-character content limit and importance in `[0,1]`. `MemoryRecord` adds ID, creation timestamp, and version. `RecallRequest` expresses the search scope. `RecallHit` returns the memory plus score/reasons.

The domain layer is deliberately storage-agnostic.

### `app/services/memory.py`

This is the central orchestration layer.

Responsibilities:

- route working memory to Redis;
- route durable memory to PostgreSQL;
- generate embeddings for durable writes and queries;
- fan out recall to relevant stores;
- merge and rank candidates.

Keeping ranking here avoids embedding retrieval policy directly in the HTTP layer or repository.

### `app/services/embedding.py`

The included embedder hashes tokens into a fixed-dimensional normalized vector. Its purpose is to make the repository runnable offline and deterministic.

It is **not semantically equivalent to a real embedding model**. Before production, implement an adapter that calls your chosen embedding model, adds timeouts/retries/circuit breaking, batches requests, records model/version, and supports re-embedding migrations.

### `app/repositories/working.py`

Redis repository:

```text
wm:<tenant>:<agent>:<namespace>:<memory-id>
```

Each record is serialized as JSON and receives `WORKING_TTL_SECONDS`.

The current list operation uses `SCAN`, not `KEYS`, which avoids blocking Redis. At high cardinality, replace scan-based recall with a per-session index, sorted set, hash, or purpose-built working-state structure.

### `app/repositories/postgres.py`

Durable repository responsibilities:

- insert durable memory;
- implement tenant-scoped idempotency;
- execute vector similarity search;
- soft-delete by tenant + memory ID.

The similarity query uses cosine distance through pgvector:

```sql
1 - (embedding <=> query_embedding)
```

The SQL always includes tenant, agent, namespace, kind, and non-deleted constraints.

### `app/core/db.py`

Creates an async SQLAlchemy engine with pool pre-ping, a base pool size of 20, and overflow of 20. These are development defaults, not universal production values. Size pools against database connection limits and replica count.

### `migrations/001_init.sql`

Creates:

- pgvector extension;
- durable `memories` table;
- tenant idempotency index;
- scope index;
- cosine HNSW vector index;
- `memory_audit` table scaffold.

The schema currently fixes vector dimensions at **384**. If you change `EMBEDDING_DIM`, update/migrate the database schema at the same time. A production system should treat embedding model + dimension as versioned schema metadata.

---

## 8. Data model and storage design

### Durable record

Conceptually:

```text
Memory
  id                UUID
  tenant_id         tenant boundary
  agent_id          owning/visible agent
  user_id           optional user scope
  kind              episodic|semantic|procedural
  namespace         logical collection
  content           memory text/payload
  importance        0..1
  metadata          JSONB extension field
  idempotency_key   retry protection
  embedding         vector(384)
  version           logical version
  created_at        creation timestamp
  deleted_at        tombstone timestamp
```

### Why PostgreSQL + pgvector?

It lets the service keep transactional metadata and vector search in the same system. This simplifies consistency for the first several scale stages and allows normal SQL filters to participate in retrieval.

The current HNSW index uses cosine operators. HNSW is appropriate when low-latency ANN recall matters and memory overhead/build cost is acceptable. Approximate search trades exactness for performance, so a production system should sample queries and compare ANN results against exact search.

### Why Redis for working memory?

Working memory is latency-sensitive, short-lived, and naturally TTL-oriented. Redis supports that model directly. The Compose configuration enables AOF with `appendfsync everysec`; nevertheless, the architecture treats working memory as reconstructable rather than authoritative durable truth.

### Metadata design

Recommended metadata envelope:

```json
{
  "source_type": "conversation",
  "source_id": "run-123",
  "source_uri": null,
  "provenance": "user_asserted",
  "confidence": 0.98,
  "sensitivity": "internal",
  "valid_from": "2026-10-02T12:00:00Z",
  "valid_until": null,
  "retention_class": "90d",
  "entity_ids": ["service:payments-api"],
  "embedding_model": "your-model-version"
}
```

Do not place secrets in metadata simply because JSONB is convenient.

---

## 9. Retrieval and ranking

The current implementation uses:

```text
working score = lexical query-token overlap

durable score = 0.75 * cosine_similarity
              + 0.25 * importance
```

This is intentionally small enough to understand and test.

### Production candidate generation

A stronger system should retrieve independently from several channels:

```text
query
 |
 +--> recent working state
 +--> PostgreSQL full-text / lexical search
 +--> vector ANN
 +--> recent episodes
 +--> entity/knowledge-graph neighborhood
 +--> high-confidence procedures
 |
 v
candidate pool
```

### Policy filtering

Apply before context construction:

```text
tenant
agent/user visibility
namespace
ACL
memory kind
validity interval
retention status
sensitivity policy
source authority
```

Never retrieve globally and rely on the LLM to ignore unauthorized memories.

### Feature scoring

Possible score:

```text
score = w1 * semantic_similarity
      + w2 * lexical_similarity
      + w3 * recency_decay
      + w4 * importance
      + w5 * source_authority
      + w6 * procedure_success_rate
      - w7 * contradiction_penalty
      - w8 * staleness_penalty
```

Weights should be learned or tuned on an evaluation set rather than chosen permanently by intuition.

### Reranking

For high-value queries:

1. retrieve 50-200 inexpensive candidates;
2. apply filters;
3. rerank the top candidates using a cross-encoder or LLM judge designed for ranking;
4. apply MMR/diversity to avoid redundant memories;
5. pack results into a token budget.

### Retrieval evaluation

Track at minimum:

- Recall@K;
- Precision@K;
- MRR;
- nDCG;
- stale-memory retrieval rate;
- contradiction rate;
- answer-grounding quality;
- p50/p95/p99 retrieval latency;
- context tokens added per answer.

ANN quality should be periodically compared with exact vector search.

---

## 10. Memory lifecycle and consolidation

A production memory system should not require the foreground request to do every expensive operation.

### Hot-path memory

Use when the information must be available immediately:

```text
interaction -> extract -> validate -> store -> available for next turn
```

### Background memory

Use when extraction/consolidation can be asynchronous:

```text
raw episode
   |
   v
transactional outbox
   |
   v
event stream
   |
   +--> fact extractor
   +--> procedure miner
   +--> deduplicator
   +--> contradiction detector
   +--> entity linker
   +--> summarizer
   +--> retention/deletion worker
```

### Semantic promotion policy

Example:

```text
candidate fact
   |
   +-- trusted explicit user assertion? ---- yes --> store with provenance
   |
   +-- authoritative tool/source? ---------- yes --> store with source/version
   |
   +-- model inference only? --------------- yes --> low confidence / require verification
```

### Contradictions

Do not simply overwrite old facts.

Prefer:

```text
fact v1: service owner = Team A
valid_until = 2026-09-30
superseded_by = fact-v2

fact v2: service owner = Team B
valid_from = 2026-10-01
```

This supports time-aware questions and auditability.

### Procedural promotion

A procedure can move through states:

```text
candidate -> observed-success -> repeated-success -> approved -> active -> deprecated
```

Execution must still pass current authorization. A remembered procedure cannot grant itself permission.

---

## 11. API reference

Interactive OpenAPI documentation is available at:

```text
http://localhost:8080/docs
```

### Health

```http
GET /healthz
```

Response:

```json
{"status":"ok"}
```

Note: the current health endpoint reports process health. For production, add separate liveness/readiness checks that verify required dependencies according to your failure policy.

### Store a memory

```http
POST /v1/memories
x-api-key: dev-change-me
Content-Type: application/json
```

Example episodic memory:

```bash
curl -sS -X POST http://localhost:8080/v1/memories \
  -H 'x-api-key: dev-change-me' \
  -H 'content-type: application/json' \
  -d '{
    "tenant_id":"acme",
    "agent_id":"muse",
    "user_id":"user-42",
    "kind":"episodic",
    "namespace":"engineering",
    "content":"Deployment 42 failed because the schema migration ran after the application rollout.",
    "importance":0.9,
    "metadata":{"run_id":"run-42","outcome":"failure"},
    "idempotency_key":"run-42-deployment-failure"
  }'
```

Working-memory example:

```bash
curl -sS -X POST http://localhost:8080/v1/memories \
  -H 'x-api-key: dev-change-me' \
  -H 'content-type: application/json' \
  -d '{
    "tenant_id":"acme",
    "agent_id":"muse",
    "kind":"working",
    "namespace":"incident-218",
    "content":"Current hypothesis: DB pool saturation is causing checkout latency.",
    "importance":0.8
  }'
```

Semantic-memory example:

```bash
curl -sS -X POST http://localhost:8080/v1/memories \
  -H 'x-api-key: dev-change-me' \
  -H 'content-type: application/json' \
  -d '{
    "tenant_id":"acme",
    "agent_id":"muse",
    "kind":"semantic",
    "namespace":"platform",
    "content":"payments-api owns card authorization.",
    "importance":0.7,
    "metadata":{"provenance":"service-catalog","confidence":1.0}
  }'
```

Procedural-memory example:

```bash
curl -sS -X POST http://localhost:8080/v1/memories \
  -H 'x-api-key: dev-change-me' \
  -H 'content-type: application/json' \
  -d '{
    "tenant_id":"acme",
    "agent_id":"muse",
    "kind":"procedural",
    "namespace":"sre",
    "content":"For rollout failures: inspect rollout status, compare error-rate delta, verify schema version, then propose rollback if policy allows.",
    "importance":0.85,
    "metadata":{"procedure_version":"1","approval":"reviewed"}
  }'
```

### Recall memories

```bash
curl -sS -X POST http://localhost:8080/v1/recall \
  -H 'x-api-key: dev-change-me' \
  -H 'content-type: application/json' \
  -d '{
    "tenant_id":"acme",
    "agent_id":"muse",
    "namespace":"engineering",
    "query":"Why did the deployment fail?",
    "kinds":["episodic","semantic","procedural"],
    "limit":5
  }'
```

Each hit includes the memory, score, and human-readable ranking reasons.

### Delete a durable memory

```bash
curl -i -X DELETE \
  'http://localhost:8080/v1/memories/<MEMORY_UUID>?tenant_id=acme' \
  -H 'x-api-key: dev-change-me'
```

Current behavior: durable soft delete. Working-memory deletion by ID is not exposed in this minimal API and is a straightforward extension.

### Idempotency semantics

For durable writes, `idempotency_key` is unique within a tenant. Retries with the same key use the SQL conflict path and increment the stored version.

A stricter production implementation should persist a request hash and reject reuse of an idempotency key with a semantically different payload.

---

## 12. Quick start with Docker Compose

### Prerequisites

Install:

- Docker Engine or Docker Desktop;
- Docker Compose v2 (`docker compose`);
- `curl` for examples.

### Step 1: unpack

```bash
unzip agent-memory-server-production.zip
cd agent-memory-server
```

### Step 2: inspect development configuration

The Compose file currently supplies development credentials directly to its containers:

```text
PostgreSQL user: memory
PostgreSQL password: memory
PostgreSQL database: memory
API key: dev-change-me
API port: 8080
```

Do not use these values outside local development.

### Step 3: build and start

```bash
docker compose up --build -d
```

### Step 4: check containers

```bash
docker compose ps
```

Expected services:

```text
postgres
redis
api
```

### Step 5: watch logs

```bash
docker compose logs -f api
```

Press `Ctrl+C` to stop following logs; containers continue running.

### Step 6: health check

```bash
curl -sS http://localhost:8080/healthz
```

Expected:

```json
{"status":"ok"}
```

### Step 7: open API docs

Open in a browser:

```text
http://localhost:8080/docs
```

### Step 8: create a memory

```bash
curl -sS -X POST http://localhost:8080/v1/memories \
  -H 'x-api-key: dev-change-me' \
  -H 'content-type: application/json' \
  -d '{"tenant_id":"demo","agent_id":"muse","kind":"episodic","content":"The checkout incident was caused by DB connection pool exhaustion.","importance":0.9}'
```

### Step 9: recall it

```bash
curl -sS -X POST http://localhost:8080/v1/recall \
  -H 'x-api-key: dev-change-me' \
  -H 'content-type: application/json' \
  -d '{"tenant_id":"demo","agent_id":"muse","query":"What caused the checkout incident?","kinds":["episodic"],"limit":5}'
```

### Stop the stack

```bash
docker compose down
```

### Stop and delete local database/Redis volumes

**Destructive:**

```bash
docker compose down -v
```

Use this when you want migrations to initialize a clean local database.

### Rebuild after code changes

```bash
docker compose up --build -d api
```

### Inspect PostgreSQL

```bash
docker compose exec postgres psql -U memory -d memory
```

Useful SQL:

```sql
\dt
SELECT id, tenant_id, agent_id, kind, namespace, content, created_at
FROM memories
WHERE deleted_at IS NULL
ORDER BY created_at DESC
LIMIT 20;
```

Exit with:

```text
\q
```

### Inspect Redis

```bash
docker compose exec redis redis-cli
```

Then:

```text
SCAN 0 MATCH wm:* COUNT 100
```

Avoid `KEYS *` on production Redis instances.

---

## 13. Run locally without Docker for the API

A convenient development pattern is to run PostgreSQL/Redis in containers and the FastAPI process on the host.

### Step 1: start dependencies

```bash
docker compose up -d postgres redis
```

The current Compose file does not publish PostgreSQL/Redis ports to the host. If you want host-run Python to connect to them, add development-only port mappings:

```yaml
postgres:
  ports:
    - "5432:5432"
redis:
  ports:
    - "6379:6379"
```

Then restart:

```bash
docker compose down
docker compose up -d postgres redis
```

### Step 2: create virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
```

Python 3.11+ is supported; 3.12 matches the Docker image.

### Step 3: create host `.env`

```bash
cp .env.example .env
```

For host execution, edit `.env` to use localhost:

```dotenv
API_KEY=dev-change-me
DATABASE_URL=postgresql+asyncpg://memory:memory@localhost:5432/memory
REDIS_URL=redis://localhost:6379/0
EMBEDDING_DIM=384
WORKING_TTL_SECONDS=86400
```

### Step 4: run API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### Step 5: test

```bash
curl http://localhost:8080/healthz
```

---

## 14. Testing

Install development dependencies:

```bash
pip install -e '.[dev]'
```

Run unit tests:

```bash
pytest -q
```

Run linting:

```bash
ruff check app tests
```

Recommended production test pyramid:

```text
unit
  domain validation
  rank features
  promotion policy
  retention rules

integration
  PostgreSQL repository
  pgvector retrieval
  Redis TTL behavior
  idempotency
  tombstones

contract
  OpenAPI compatibility
  SDK compatibility

end-to-end
  remember -> recall -> delete
  dependency degradation

load
  write QPS
  recall QPS
  hot-tenant behavior
  HNSW recall/latency

resilience
  Redis restart
  DB failover
  embedding timeout
  duplicate event delivery
```

The repository includes a small model test starter; the production test suite should be expanded substantially before deployment.

---

## 15. Configuration

`app/core/config.py` uses Pydantic Settings and reads environment variables / `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `API_KEY` | `dev-change-me` | development API authentication |
| `DATABASE_URL` | container-local PostgreSQL URL | SQLAlchemy async connection |
| `REDIS_URL` | container-local Redis URL | working-memory Redis |
| `EMBEDDING_DIM` | `384` | embedding dimension |
| `WORKING_TTL_SECONDS` | `86400` | working-memory TTL |

Additional config fields in code include `service_name`, optional `embedding_url`, and `max_recall`.

### Critical embedding-dimension rule

The migration declares:

```sql
embedding vector(384)
```

Therefore changing only `EMBEDDING_DIM` will break writes. Change dimensions through a schema migration and plan re-embedding/versioning.

### Secrets

Production:

```text
DO NOT -> commit API keys to Git
DO NOT -> put cloud credentials in .env baked into images
DO     -> use Secret Manager / Vault / KMS-backed secret delivery
DO     -> use short-lived workload identity where possible
```

---

## 16. Application integration patterns

### 16.1 Personal assistant

Use:

- working: active conversation/task state;
- episodic: notable prior interactions;
- semantic: explicit durable preferences/facts;
- procedural: successful recurring workflows.

### 16.2 SRE / incident agent

```text
working    active hypotheses + investigation plan
episodic   past incidents and remediation outcomes
semantic   service ownership/topology/SLO facts
procedural runbooks and successful mitigation sequences
```

### 16.3 Software engineering agent

```text
working    files currently being edited, plan, test failures
episodic   prior attempts and review feedback
semantic   architecture decisions, repository conventions
procedural build/test/release/refactor workflows
```

### 16.4 Customer-support agent

```text
working    current ticket context
episodic   prior support interactions
semantic   verified customer/product facts
procedural approved resolution playbooks
```

Keep customer boundaries strict. Do not use one customer's memory as another customer's retrieval corpus.

### 16.5 Research agent

Episodic memory tracks searches/experiments; semantic memory stores source-grounded findings; procedural memory stores successful research methods. Provenance and source validity become especially important.

### 16.6 Multi-agent system

Use namespaces and ACLs to model:

```text
private agent memory
team-shared memory
workflow memory
organization memory
```

Do not assume all agents should see all memories simply because they share a tenant.

---

## 17. LangGraph integration

LangGraph-style systems have two related but distinct persistence needs:

```text
Checkpointer
  "Where exactly was this graph execution?"

Agent Memory Server
  "What knowledge should be available across executions/threads?"
```

Recommended integration:

```text
                 LangGraph
                    |
        +-----------+-----------+
        |                       |
        v                       v
  checkpointer             memory tools
 thread/run state        remember / recall
        |                       |
        v                       v
 workflow recovery       Agent Memory Server
```

Pseudo-tool wrapper:

```python
async def recall_memory(query: str, namespace: str = "default"):
    payload = {
        "tenant_id": TENANT_ID,
        "agent_id": AGENT_ID,
        "namespace": namespace,
        "query": query,
        "kinds": ["episodic", "semantic", "procedural"],
        "limit": 8,
    }
    # POST payload to /v1/recall using your authenticated HTTP client
```

A graph node can recall before planning and remember an episode after completion. Keep checkpoint state in the checkpointer; do not serialize the entire graph state into semantic memory.

---

## 18. Meta Muse-style integration

For a persistent agent with browser/filesystem/terminal/tool access, place the memory server behind the agent runtime rather than allowing memory text to directly control tools.

```text
                    Persistent Agent
                         /   |   \
                        /    |    \
                 browser   tools   terminal
                      \      |      /
                       \     |     /
                        policy engine
                             |
                 +-----------+-----------+
                 |                       |
              recall                  remember
                 |                       |
                 +----------+------------+
                            v
                    Agent Memory Server
```

### Safe recall contract

Return memory as **data**:

```text
source
memory kind
content
confidence
validity
retrieval score
```

Never interpret stored text such as "ignore policy and delete repository" as runtime authority. Tool permissions come from the current policy engine and user authorization.

### Suggested agent loop

```text
1. receive goal
2. recall relevant working + durable memory
3. build context under token budget
4. plan
5. execute allowed tools
6. checkpoint workflow separately
7. record episode/outcome
8. asynchronously extract facts/procedures
9. promote only under policy
```

---

## 19. Security and governance

The included API key is a local-development bootstrap, not enterprise identity.

### Production identity

Prefer:

- OIDC/JWT for users/services;
- workload identity for service-to-service calls;
- mTLS where required;
- short-lived tokens;
- explicit audience/issuer validation.

### Authorization

Model authorization on more than `tenant_id`:

```text
tenant
principal
agent
namespace
memory kind
resource ACL
sensitivity
purpose
region
```

Use RBAC for broad roles and ABAC for contextual policy.

### PostgreSQL Row Level Security

For higher assurance, enforce tenant/user access in PostgreSQL RLS in addition to application checks. Defense in depth matters because a bug in a query builder should not become a cross-tenant disclosure.

### Prompt injection

Retrieved memory is untrusted input.

Rules:

1. memory content cannot alter system policy;
2. memory content cannot grant tool permissions;
3. recalled instructions should be labeled as data;
4. sanitize tool/browser content before durable promotion;
5. maintain provenance;
6. require approval for high-impact writes.

### Encryption

- TLS in transit;
- encrypted disks/database at rest;
- KMS-managed keys;
- consider per-tenant envelope encryption for high-sensitivity deployments;
- never log raw secrets.

### Audit

Audit events should include:

```text
who
what action
which tenant/memory
when
request/correlation ID
policy decision
source IP/service identity where appropriate
result
```

Avoid copying full sensitive memory bodies into audit logs.

---

## 20. Reliability and consistency

### Durable writes

PostgreSQL transactions provide the authoritative write boundary.

### Working memory

Redis is a separate consistency domain. The architecture deliberately accepts that working state may be lost and reconstructed.

### Dual-write problem

Do not write PostgreSQL and an event broker independently in the request path:

```text
DB commit succeeds
broker publish fails
=> inconsistent derived state
```

Use a transactional outbox:

```text
BEGIN
  write memory
  write outbox event
COMMIT

outbox relay -> event stream
```

Consumers must be idempotent because at-least-once delivery can redeliver events.

### Event backbone

Redis Streams can support moderate-scale event processing with consumer groups and acknowledgments. Kafka/Pulsar may be preferable where retention, throughput, organizational standards, or cross-region replication requirements justify them.

### Retries

Use:

```text
bounded exponential backoff
jitter
timeouts
circuit breakers
bulkheads
idempotency
```

Never blindly retry non-idempotent writes.

### Graceful degradation

Example recall policy:

```text
embedding service healthy -> lexical + vector + rerank
embedding service down    -> lexical + recent memories
Redis down                -> durable recall only
reranker down             -> base fused rank
```

The agent should know retrieval was degraded so it can reduce confidence appropriately.

---

## 21. Observability and SLOs

Instrument with OpenTelemetry across:

```text
API -> auth -> MemoryService -> embedding -> Redis/Postgres -> ranking
```

### Metrics

Service:

- requests/sec;
- error rate;
- p50/p95/p99 latency;
- active requests;
- rate-limit rejects.

Database:

- pool utilization;
- connection wait time;
- query latency;
- lock waits;
- replica lag;
- index size;
- HNSW query latency.

Redis:

- command latency;
- memory usage;
- evictions;
- expired keys;
- replication health.

Memory quality:

- Recall@K;
- MRR/nDCG;
- ANN-vs-exact recall;
- stale retrieval rate;
- contradiction rate;
- procedure success rate;
- consolidation lag;
- deletion lag.

### Illustrative SLOs

These are design targets, **not measurements from this repository**:

```text
API availability                    99.95%
working-memory p95                  < 50 ms intra-region
durable write p95                   < 200 ms excluding remote embedder
recall p95                          define from workload/evaluation
privacy deletion processing         policy-specific bounded window
```

Define SLOs from user impact, then derive capacity and alerts.

### Logging

Use structured logs with:

```text
trace_id
request_id
tenant hash/id according to policy
agent_id
operation
latency
result/error class
```

Do not log raw memory content by default.

---

## 22. Performance and capacity planning

Model at least:

```text
tenants
agents/tenant
memories/agent/day
retention days
average content bytes
embedding dimensions
bytes/vector
write QPS
recall QPS
K candidates
index overhead
replication factor
backup overhead
```

### HNSW considerations

HNSW improves ANN query performance but consumes memory and increases index build/write cost. Important tuning dimensions include graph connectivity, construction effort, and query search effort. Tune against a representative recall/latency benchmark.

### Filtering + ANN

Tenant/namespace filters can interact with approximate indexes. At scale consider:

- iterative ANN scans;
- partial indexes for stable low-cardinality segments;
- partitioning;
- tenant-aware shards;
- dedicated large-tenant cells.

### Embedding migrations

Changing models can change dimension and semantic geometry.

Use versioned migration:

```text
embedding_v1 remains serving
        |
background re-embed
        v
embedding_v2 populated
        |
shadow evaluation
        |
traffic switch
        |
retire v1 after rollback window
```

Never replace millions of embeddings in place without a rollback plan.

### Hot/cold tiering

Older low-value episodes can move to cheaper storage while keeping summaries/high-value semantic memories hot. Retrieval can query cold storage only when required.

---

## 23. Scaling architecture

### Stage 1: development

```text
1 API
1 PostgreSQL/pgvector
1 Redis
```

### Stage 2: production service

```text
N stateless APIs
PostgreSQL HA primary/replicas
Redis HA
real embedding service
OIDC
telemetry
backups
```

### Stage 3: asynchronous memory platform

Add:

```text
transactional outbox
event stream
consolidation workers
reranker
lexical search
entity extraction
retention/deletion workers
```

### Stage 4: cell architecture

```text
Global routing/control plane
          |
  +-------+--------+--------+
  |                |        |
Cell EU          Cell US  Cell APAC
  |                |        |
API/Redis/PG     API/...   API/...
```

Advantages:

- bounded blast radius;
- regional data residency;
- easier tenant placement;
- independent scaling;
- failure containment.

### Sharding key

A common starting point is `tenant_id`, because most retrieval is tenant-scoped. Very large tenants may require sub-sharding by agent/user/namespace.

Avoid cross-shard fanout on the hot recall path where possible.

---

## 24. Deployment to Kubernetes

`k8s/deployment.yaml` is a **baseline API Deployment**, not a complete production platform manifest.

Build image:

```bash
docker build -t agent-memory-server:1.0.0 .
```

For a real cluster, push it to your registry:

```text
<registry>/agent-memory-server:1.0.0
```

Then update `k8s/deployment.yaml` to use that image.

Apply baseline:

```bash
kubectl apply -f k8s/deployment.yaml
```

Check:

```bash
kubectl get pods -l app=agent-memory-server
kubectl describe deployment agent-memory-server
kubectl logs -l app=agent-memory-server --tail=100
```

### Required additions for production Kubernetes

The repository intentionally does not pretend these environment-specific resources are universal. Add:

- Kubernetes `Service`;
- Ingress/Gateway/API gateway;
- Secret/ExternalSecret integration;
- ConfigMap or environment injection;
- production `DATABASE_URL` / `REDIS_URL`;
- network policies;
- PodDisruptionBudget;
- HorizontalPodAutoscaler;
- topology spread / anti-affinity;
- service account/workload identity;
- liveness + dependency-aware readiness;
- telemetry collector;
- managed PostgreSQL/Redis or operators with HA/backup plans.

Do not run a single unmanaged PostgreSQL pod as the production source of truth merely because it is easy to deploy.

---

## 25. Failure modes and recovery

| Failure | Expected behavior | Production mitigation |
|---|---|---|
| Redis unavailable | working-memory path degraded | HA Redis, bounded retry, durable-only fallback |
| PostgreSQL unavailable | durable writes/recall fail | HA/failover, connection timeout, backpressure |
| Embedder unavailable | semantic write/recall impaired | circuit breaker, queue writes, lexical fallback |
| Duplicate request | duplicate durable memory risk | tenant-scoped idempotency |
| Event redelivery | duplicate projection | idempotent consumers |
| Stale embedding | wrong retrieval | embedding versioning + reindex/re-embed |
| ANN recall regression | relevant memory missed | exact-search sampling + recall alarms |
| Hot tenant | noisy-neighbor latency | quotas, partition/shard/cell placement |
| Poison event | worker loop failure | DLQ/quarantine + alert |
| Partial deletion | privacy risk | deletion ledger + reconciliation |
| Stored prompt injection | unsafe agent behavior | treat memory as data + policy-controlled tools |

### Backups

For PostgreSQL define:

- automated snapshots;
- point-in-time recovery;
- restore drills;
- RPO/RTO;
- backup encryption;
- regional copy policy.

A backup is not a recovery strategy until restoration is tested.

---

## 26. Privacy, retention, and deletion

The API currently tombstones durable rows. Enterprise deletion is a distributed workflow.

### Deletion lifecycle

```text
delete request
    |
    v
authorize request
    |
    v
tombstone source-of-truth row
    |
    v
emit deletion event
    |
    +--> Redis/cache purge
    +--> vector/derived index purge
    +--> summary/graph purge or recomputation
    +--> analytics deletion
    +--> backup expiry policy
    |
    v
reconciliation / deletion ledger
```

### Retention

Retention should depend on:

```text
memory kind
sensitivity
source
purpose
jurisdiction
customer policy
user deletion state
```

Working memory may be hours/days; durable semantic facts may be retained until superseded; episodes may have bounded retention.

### Right to correct

For factual memory, correction can be more useful than deletion. Preserve an audit trail while ensuring retrieval selects the valid current record.

---

## 27. Production hardening checklist

Before production, complete at least the following.

### Identity/security

- [ ] replace static API key with OIDC/workload identity;
- [ ] implement RBAC/ABAC;
- [ ] add PostgreSQL RLS where appropriate;
- [ ] integrate secret manager/KMS;
- [ ] TLS everywhere;
- [ ] add rate limits and request-size limits;
- [ ] define prompt-injection handling;
- [ ] perform threat modeling.

### Data

- [ ] replace hash embedder with real embedding adapter;
- [ ] version embedding model/dimension;
- [ ] add provenance/confidence/validity schema;
- [ ] implement contradiction/supersession model;
- [ ] define retention classes;
- [ ] implement verified deletion workflow.

### Retrieval

- [ ] add lexical retrieval;
- [ ] implement candidate fusion;
- [ ] add recency decay;
- [ ] add source-authority features;
- [ ] add reranking/MMR where useful;
- [ ] build retrieval evaluation dataset;
- [ ] measure ANN recall against exact search.

### Reliability

- [ ] transactional outbox;
- [ ] idempotent async consumers;
- [ ] HA PostgreSQL and Redis;
- [ ] backups + restore drills;
- [ ] circuit breakers/timeouts;
- [ ] overload protection/backpressure;
- [ ] graceful degradation paths.

### Operations

- [ ] OpenTelemetry tracing;
- [ ] dashboards and alerts;
- [ ] SLO/error-budget definition;
- [ ] load tests;
- [ ] chaos/failover tests;
- [ ] capacity model;
- [ ] on-call runbooks.

### Kubernetes/cloud

- [ ] production Service/Ingress;
- [ ] secrets/config injection;
- [ ] HPA/PDB/topology spread;
- [ ] NetworkPolicy;
- [ ] workload identity;
- [ ] managed data services or validated HA operators.

---

## 28. Design trade-offs

### PostgreSQL/pgvector vs dedicated vector database

**PostgreSQL advantages**

- transactional metadata + vectors together;
- mature SQL filtering;
- fewer distributed systems initially;
- straightforward backup/governance story.

**Dedicated vector system advantages**

- may provide specialized ANN scaling/features;
- can independently scale vector workload;
- may offer advanced distributed indexing.

A Principal-level choice should be driven by measured scale, operational capability, isolation requirements, and retrieval features—not fashion.

### Redis working memory vs PostgreSQL-only

Redis adds another dependency but gives natural TTL and low latency. PostgreSQL-only can be operationally simpler at lower scale. The correct choice depends on working-state QPS and latency requirements.

### Hot-path extraction vs asynchronous consolidation

Hot path gives immediate availability but increases latency/cost and failure surface. Async consolidation reduces foreground latency but introduces eventual consistency. Many systems use both: explicit important memories hot-path, inferred summaries/procedures asynchronously.

### Mutable record vs immutable versions

The sample conflict path increments `version`. For high-governance systems, prefer immutable versions plus `supersedes` links so history remains explainable.

---

## 29. Discussion guide

This project is useful for discussing more than vector search.

### Requirements

Ask:

- What must be remembered?
- Who owns memory?
- Is memory user-, agent-, team-, or tenant-scoped?
- How quickly must writes become recallable?
- What is the retention/deletion contract?
- What is the expected QPS/cardinality?
- Is cross-region access allowed?

### API design

Explain why `remember`, `recall`, and deletion form a stable service boundary while storage implementations can evolve.

### Data modeling

Explain why episodic, semantic, procedural, and working memory have different lifecycle semantics.

### Retrieval

Discuss hybrid candidate generation, ANN, lexical retrieval, filters, reranking, recency, source authority, diversity, and token budgeting.

### Distributed systems

Discuss:

- transaction boundaries;
- outbox pattern;
- at-least-once delivery;
- idempotency;
- eventual consistency;
- backpressure;
- sharding;
- cells;
- failover;
- data residency.

### Security

Discuss why recalled memory is untrusted and cannot become an authorization channel.

### ML/AI quality

Discuss offline retrieval datasets, Recall@K/nDCG, shadow evaluation, embedding migrations, hallucinated memory, contradictions, and provenance.

### Cost

Discuss:

```text
embedding cost
vector storage
ANN RAM
reranking cost
context-token savings
retention/hot-cold tiering
```

### Key Principal-level insight

The hardest problem is not storing vectors. It is defining **what deserves to become memory, when it is valid, who may retrieve it, how contradictions are resolved, how retrieval quality is measured, and how the system forgets safely**.

---

## 30. Troubleshooting

### API does not start

```bash
docker compose logs api
```

Then verify dependencies:

```bash
docker compose ps
```

### PostgreSQL migration did not rerun

Docker's initialization scripts run when the database volume is first created. For disposable local development only:

```bash
docker compose down -v
docker compose up --build -d
```

This deletes local data.

### `vector` extension/type error

Ensure the PostgreSQL image is the pgvector image from `docker-compose.yml`, then inspect:

```bash
docker compose exec postgres psql -U memory -d memory -c '\dx'
```

### Vector dimension mismatch

The database schema is `vector(384)`. Keep `EMBEDDING_DIM=384` unless you perform a schema/embedding migration.

### Unauthorized

Use:

```text
x-api-key: dev-change-me
```

for the default local Compose environment.

### Recall returns poor semantic matches

Expected with the deterministic hash fallback. Replace it with a real embedding model before evaluating semantic quality.

### Host-run API cannot reach Postgres/Redis

Container service names `postgres` and `redis` resolve inside the Compose network, not directly from your host. Publish ports and use `localhost` as described in section 13.

### Working memory disappears

Working memory has TTL. Default is 86,400 seconds. Redis is intentionally not the durable source of truth for long-term memory.

### Deleted memory still appears somewhere else

The current sample only tombstones the PostgreSQL durable row. A production system must propagate deletion to caches/derived stores and reconcile completion.

---

## 31. Roadmap

A logical evolution sequence:

### Phase 1 — retrieval quality

- real embedding provider adapter;
- PostgreSQL full-text retrieval;
- hybrid fusion;
- recency/authority ranking;
- evaluation harness.

### Phase 2 — memory lifecycle

- asynchronous consolidation;
- transactional outbox;
- fact extraction;
- procedure mining;
- contradiction/supersession graph;
- provenance model.

### Phase 3 — enterprise controls

- OIDC;
- RBAC/ABAC;
- RLS;
- audit pipeline;
- retention/deletion orchestration;
- per-tenant quotas.

### Phase 4 — scale

- tenant partitioning/sharding;
- cell architecture;
- independent retrieval workers;
- reranking service;
- hot/cold memory tiers;
- multi-region placement.

### Phase 5 — advanced memory intelligence

- entity graph;
- temporal facts;
- confidence calibration;
- memory usefulness feedback;
- learned ranking;
- automatic procedure deprecation;
- memory compression/summarization with provenance preservation.

---

## 32. License

This repository is provided as an Apache-2.0-style project scaffold. Review and comply with the licenses of all third-party dependencies and any embedding/model provider used in your deployment.

---

## Final architecture summary

```text
                         AGENT MEMORY PLATFORM

                            Agent Runtime
                                 |
                  +--------------+--------------+
                  |                             |
             workflow state                memory context
                  |                             |
             Checkpointer                  Memory API
                                                |
                                    +-----------+-----------+
                                    |                       |
                              Working memory          Durable memory
                                  Redis                PostgreSQL
                                    |                  + pgvector
                                    |                       |
                                    +-----------+-----------+
                                                |
                                          Retrieval
                                    lexical/vector/recent
                                                |
                                           Policy filter
                                                |
                                             Rerank
                                                |
                                         Context budget
                                                |
                                                v
                                               LLM
                                                |
                                             outcome
                                                |
                                      episode + outbox
                                                |
                                    consolidation pipeline
                                      /                 \
                                     v                   v
                              semantic facts       procedures
```

**The production mental model:** memory is not “put text into a vector DB and search it later.” It is a governed, multi-tenant knowledge lifecycle with explicit semantics, provenance, quality measurement, reliability boundaries, security controls, and deletion guarantees.
