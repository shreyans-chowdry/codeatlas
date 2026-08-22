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

### Prerequisites
- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- Account API Keys for:
  - **[Voyage AI](https://www.voyageai.com/)** (for `voyage-code-3` code embeddings)
  - **[Anthropic](https://www.anthropic.com/)** (for `claude-3-5-sonnet` RAG answers)
  - **[Supabase / Postgres](https://supabase.com/)** (PostgreSQL instance with `pgvector` extension enabled)

### Running with Docker Compose

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-user/codeatlas.git
   cd codeatlas
   ```

2. **Configure Environment Variables:**
   Copy `.env.example` to `.env` and fill in your connection strings and API keys:
   ```bash
   cp .env.example .env
   ```

3. **Start the Platform:**
   ```bash
   docker compose up --build
   ```

4. **Access the Web App:**
   - **Frontend:** `http://localhost:3000`
   - **FastAPI Backend Docs:** `http://localhost:8000/docs`

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
