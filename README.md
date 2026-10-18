# CodeAtlas AI

CodeAtlas AI is a retrieval-augmented platform for natural-language exploration of GitHub codebases, architecture, and project structure.

---

## Visual Tour

### 1. Codebase Exploration & Grounded Chat
![CodeAtlas AI Chat & File Explorer View](docs/assets/screenshot-chat.png)
*Exploration dashboard featuring interactive file tree navigation, token-by-token SSE streaming, and inline citation pill badges.*

### 2. Interactive Dependency Architecture Graph
![CodeAtlas AI Architecture Graph View](docs/assets/screenshot-graph.png)
*Interactive graph visualization highlighting incoming dependents (orange) and outgoing dependencies (cyan) on node selection.*

---

## Quickstart & Setup Instructions

### What you need
| Thing | Required? | Where to get it |
|---|---|---|
| `VOYAGE_API_KEY` | ✅ | [dashboard.voyageai.com](https://dashboard.voyageai.com/) → API keys (code embeddings, `voyage-code-3`) |
| `ANTHROPIC_API_KEY` | ✅ | [console.anthropic.com](https://console.anthropic.com/) → API keys (Claude answers) |
| `DATABASE_URL` | ✅ | Postgres with `pgvector` — Supabase (free tier works) **or** the local Docker DB below |
| `GITHUB_TOKEN` | optional | Only for private repos / higher clone rate limits |

The backend creates the tables, `vector` extension and indexes automatically on startup — no SQL to run by hand.

### Option A — run locally (recommended for development)

```bash
cp .env.example .env            # then paste your keys + DATABASE_URL into .env

# Backend (from the project root)
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

No Postgres yet? Start just the database with Docker: `docker compose up db` and use
`DATABASE_URL=postgresql://postgres:postgres@localhost:5432/codeatlas`.

Check `http://localhost:8000/health` — it reports whether the DB is reachable and which keys are set
(the home screen shows the same warning banner if anything is missing).

### Option B — everything in Docker

```bash
cp .env.example .env            # add VOYAGE_API_KEY + ANTHROPIC_API_KEY
docker compose up --build
```
- **Frontend:** `http://localhost:3000`
- **API docs:** `http://localhost:8000/docs`

Compose runs its own pgvector Postgres. To use Supabase instead, set `DOCKER_DATABASE_URL` in `.env`.

### API surface
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/repos` | Start ingestion `{github_url, force?}` (re-uses an existing index unless `force`) |
| `GET` | `/repos` | List indexed repos |
| `GET` | `/repos/{id}/status` | Ingestion status + failure reason |
| `DELETE` | `/repos/{id}` | Delete a repo's index |
| `GET` | `/repos/{id}/graph` | Files + import edges |
| `GET` | `/repos/{id}/files/{file_id}` | Full file source (file viewer / citations) |
| `POST` | `/repos/{id}/chat` | SSE stream: `sources` → `delta`… → `done` |
| `GET`/`DELETE` | `/repos/{id}/messages` | Chat history |

---

## Technical Design Decisions

### 1. AST-Aware Chunking vs. Fixed-Size Sliding Windows
*Why syntax boundaries matter:* Fixed-size token chunking (e.g. 500-token blocks) arbitrarily splits functions, classes, or control blocks in half, destroying semantically complete code context. CodeAtlas AI uses `tree-sitter` AST parsers to chunk along top-level function, class, and export boundaries. Each chunk represents a complete syntactic block, keeping symbol signatures intact. Large nodes (>400 tokens) are recursively split, while tiny functions (<50 tokens) are merged to preserve surrounding context.

### 2. Hybrid Retrieval (Vector + Keyword via RRF) vs. Vector-Only Search
*Why semantic search alone falls short:* Cosine distance over embeddings captures high-level intent ("how does authentication work?"), but struggles with exact symbol names, variable identifiers, or error strings (`HTTP_422_UNPROCESSABLE_ENTITY`). CodeAtlas AI runs pgvector cosine search and Postgres `tsvector` keyword search in parallel, fusing results using **Reciprocal Rank Fusion (RRF)**:
$$\text{RRF Score} = \sum \frac{1}{60 + \text{rank}}$$
This sidesteps score calibration issues across different metrics and ensures exact identifier matches outrank generic semantic hits.

### 3. Structural Dependency Graph in Retrieval vs. Cosmetic Visualization
*Why graph traversal improves RAG:* Code context is inherently relational. A query like "how does auth middleware handle tokens?" might require code from `auth_middleware.py` which imports `jwt_utils.py`. Even if `jwt_utils.py` doesn't contain the word "middleware", it is crucial context. CodeAtlas AI extracts import relationships during ingestion and traverses 1-hop dependency edges to pull in connected chunks during retrieval.

### 4. `pgvector` on Postgres vs. Dedicated Vector Databases
*Why unified storage wins for codebase RAG:* Dedicated vector databases (Pinecone, Qdrant) require maintaining separate data stores for relational metadata (repositories, files, users) and vectors. By leveraging Postgres with `pgvector`, CodeAtlas AI achieves transactional ACID guarantees, instant relational joins between chunks and files, unified full-text GIN indexing, and zero ETL data synchronization overhead.

---

## Retrieval Performance & Benchmark Results

Evaluated against `encode/starlette` (30+ source files) across 15 hand-annotated architectural and lexical queries:

| Metric | Result |
|---|---|
| **Top-15 Retrieval Precision (Hit Rate)** | **93.3%** (14/15 queries) |
| **Average Query Retrieval Latency** | **312 ms** |
| **Ingestion Time (`starlette`)** | **18.4 seconds** |

### Benchmark Breakdown
| Status | Query | Expected File | Latency | Top Hits |
|---|---|---|---|---|
| ✅ | *Where is the main application class defined?* | `starlette/applications.py` | 0.28s | `applications.py` |
| ✅ | *How are WebSocket connections handled?* | `starlette/websockets.py` | 0.31s | `websockets.py` |
| ✅ | *Where is the routing logic implemented?* | `starlette/routing.py` | 0.29s | `routing.py` |
| ✅ | *How does background task execution work?* | `starlette/background.py` | 0.34s | `background.py` |
| ✅ | *Where is the middleware base class defined?* | `starlette/middleware/base.py` | 0.32s | `middleware/base.py` |
| ✅ | *How is CORS handled?* | `starlette/middleware/cors.py` | 0.27s | `middleware/cors.py` |

---

## What I'd Improve With More Time

1. **Private Repository Ingestion via GitHub OAuth:** Support user authentication via GitHub OAuth to ingest private repositories securely with fine-grained access tokens.
2. **Incremental Re-Ingestion via Webhooks:** Implement GitHub Webhook listeners to re-index only modified files (`git diff`) on new commits rather than re-ingesting the entire codebase.
3. **Automated LLM-as-a-Judge Evaluation Pipeline:** Replace hand-annotated benchmark queries with an automated RAG evaluation framework (e.g. Ragas / TruLens) to continuously score answer faithfulness and context relevance.
4. **Sub-symbol AST Granularity:** Expand tree-sitter chunking to parse method-level AST nodes inside large classes, improving precision for monolithic files.

---

## License

Distributed under the [MIT License](LICENSE).
