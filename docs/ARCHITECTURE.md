# CodeAtlas AI — Technical Architecture & Pipeline Walkthrough

This document provides an in-depth technical walkthrough of CodeAtlas AI's ingestion, retrieval, and streaming LLM pipelines. It is written for developers reading the codebase for the first time.

---

## High-Level Architecture Overview

CodeAtlas AI is a retrieval-augmented generation (RAG) platform designed specifically for natural-language code exploration. Unlike generic document RAG systems, CodeAtlas AI treats source code as a structured syntax tree and a directed dependency graph.

```
[Public GitHub Repo]
        │
        ▼
[Ingestion Pipeline]
  ├── Git Shallow Clone (github_fetch.py)
  ├── Binary & Language Filtering (file_walker.py)
  ├── AST-Aware Chunking (chunker.py using tree-sitter)
  ├── Import & Graph Resolution (dependency_graph.py)
  └── Vector Embeddings (embedder.py using voyage-code-3)
        │
        ▼
[Supabase / Postgres (pgvector)]
  ├── Repos, Files, Chunks, DependencyEdges, ChatMessages
        │
        ▼
[Hybrid Retrieval Pipeline] (retrieve in pipeline.py)
  ├── Parallel Vector Search (pgvector HNSW cosine distance)
  ├── Parallel Keyword Search (tsvector / ts_rank GIN)
  ├── Reciprocal Rank Fusion (hybrid_rank.py)
  └── Dependency Graph Expansion (graph_expand.py)
        │
        ▼
[LLM Streaming Engine] (claude_client.py)
  └── Grounded Citation Prompt → Claude → FastAPI SSE Stream
```

---

## 1. Database Schema (`backend/app/db/models.py`)

The system relies on five main entities stored in Postgres (with `pgvector` enabled):

1. **`Repo`**: Stores metadata (`github_url`, `name`, `status`, `file_count`).
2. **`File`**: Represents individual source files within a repo (`path`, `language`).
3. **`Chunk`**: Stores discrete code blocks with start/end line bounds, `symbol_name`, AST source content, and a 1024-dimensional `embedding` vector (`pgvector`). Also indexed with a generated `content_tsvector` column for full-text keyword search.
4. **`DependencyEdge`**: Represents directed dependency relationships (`source_file_id` -> `target_file_id`, `edge_type="imports"`).
5. **`ChatMessage`**: Persists conversation turns (`role`, `content`, timestamp).

---

## 2. Ingestion Pipeline (`backend/app/ingestion/`)

The ingestion pipeline runs as a FastAPI `BackgroundTask` upon receiving a `POST /repos` request.

### Step 2.1: Shallow Clone (`github_fetch.py`)
- Executes a shallow git clone (`depth=1`) into a temporary working directory using `GitPython`.
- Restricts operations to public GitHub repositories to prevent unauthorized access or credential leak risks.

### Step 2.2: File Walking & Filtering (`file_walker.py`)
- Walks the repository directory while ignoring standard noise directories (`node_modules`, `.git`, `venv`, `__pycache__`, `.next`, `dist`, `build`).
- Inspects the first 4KB of each file for null bytes (`\x00`) to filter out binary files.
- Skips files exceeding 1MB in size.
- Restricts files to an explicit allowlist of source extensions (`.py`, `.js`, `.ts`, `.tsx`, `.java`, `.go`, `.rs`, `.c`, `.cpp`, `.rb`).

### Step 2.3: AST-Aware Chunking (`chunker.py`)
- Uses `tree-sitter` bindings to parse source files into Abstract Syntax Trees.
- Identifies top-level syntax boundaries: `function_definition`, `class_definition`, `export_statement`, etc.
- Each chunk preserves its exact source code boundaries (`start_line`, `end_line`, `symbol_name`).
- **Overlarge Nodes (>400 tokens):** Recursively split using a sliding window with overlap.
- **Tiny Functions (<50 tokens):** Merged sequentially into contiguous blocks to avoid retrieval fragmentation.

### Step 2.4: Dependency Extraction & Resolution (`dependency_graph.py`)
- **Python:** Parses imports using Python's native `ast` module (avoids string/comment false positives).
- **JS/TS:** Uses `tree-sitter` AST nodes to extract `import` and `require` specifiers.
- **Resolution:** Maps import paths (e.g. `./utils` or `app.services`) to ingested files in the repo using relative resolution rules and extension candidates (`.py`, `.ts`, `index.ts`, `__init__.py`).
- Writes matching links as `DependencyEdge` rows in Postgres.

### Step 2.5: Code Embeddings (`embedder.py`)
- Batches chunks (up to 100 per API request) and calls Voyage AI (`voyage-code-3` model).
- Specifies `input_type="document"` to optimize embeddings for indexing.
- Includes automatic retry-with-backoff for 429 rate limits.
- Persists Chunks, Files, and DependencyEdges to Postgres in a single atomic transaction and sets `Repo.status = "ready"`.

---

## 3. Hybrid Retrieval Pipeline (`backend/app/retrieval/`)

Retrieval combines semantic search, keyword search, and structural graph traversal in a unified pipeline orchestrated by `retrieve()` in `backend/app/retrieval/pipeline.py`.

```
Query -> Embed Query (Voyage input_type="query")
             │
     ┌───────┴───────┐
     ▼               ▼
Vector Search   Keyword Search  (Parallel Execution)
(Cosine <=> )    (ts_rank GIN)
     │               │
     └───────┬───────┘
             ▼
Reciprocal Rank Fusion (RRF: sum(1 / (60 + rank)))
             │
             ▼
Dependency Graph Expansion (Fetch 1-hop connected chunks)
             │
             ▼
  Final Context Payload
```

### Step 3.1: Dual Parallel Search
1. **Vector Search (`vector_search.py`):** Embeds the user query using `voyage-code-3` with `input_type="query"`. Runs an HNSW cosine similarity search (`Chunk.embedding <=> query_vec`) scoped to `repo_id`.
2. **Keyword Search (`keyword_search.py`):** Runs Postgres `ts_rank` against `content_tsvector` using `plainto_tsquery`. Catches exact symbol names, error codes, and literal function names that vector similarity might miss.
3. Both searches execute concurrently using a `ThreadPoolExecutor`.

### Step 3.2: Reciprocal Rank Fusion (`hybrid_rank.py`)
- Fuses vector and keyword search results using RRF:
  $$\text{RRF Score} = \sum \frac{1}{60 + \text{rank}}$$
- Avoids fragile score normalization across incomparable scales (cosine similarity 0..1 vs `ts_rank` non-negative float).
- Chunks appearing in both lists automatically outrank single-list hits.

### Step 3.3: Dependency Graph Expansion (`graph_expand.py`)
- Inspects the top 5 ranked chunks and finds their file IDs.
- Queries `DependencyEdge` for 1-hop neighbours (files imported by or importing the seed files).
- Pulls top chunks from connected files even if they didn't rank high in vector or keyword search.
- **Why this matters:** Allows answering architectural questions (e.g. "How does auth middleware work?") even when the target middleware file doesn't explicitly contain the query's keywords.

---

## 4. LLM Streaming & SSE (`backend/app/llm/` & `backend/app/routers/chat.py`)

1. **Prompt Construction (`claude_client.py`):** Formats retrieved chunks with explicit headers:
   ```
   ### path/to/file.py (lines 12-45)
   ```code...```
   ```
2. **System Prompt Grounding:** Enforces strict grounding rules:
   - Answer *only* using provided context.
   - Explicitly state when context is insufficient rather than hallucinating.
   - Cite source file paths and line ranges for all statements.
3. **SSE Streaming:** FastAPI streams tokens as Server-Sent Events (`data: {"type": "delta", "text": "..."}\n\n`).
4. **Resilient Persistence:** To handle client disconnects, user messages are saved immediately, and the complete assistant response is persisted via a FastAPI `BackgroundTask` rather than relying on generator cleanup.
