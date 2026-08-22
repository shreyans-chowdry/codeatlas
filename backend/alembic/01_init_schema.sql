-- 1. Enable pgvector extension for embedding support
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create custom enum type for Repo status
CREATE TYPE repo_status AS ENUM ('pending', 'ingesting', 'ready', 'failed');

-- 3. Create Tables

CREATE TABLE repos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_url VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    status repo_status NOT NULL DEFAULT 'pending',
    file_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    path VARCHAR NOT NULL,
    language VARCHAR
);

CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    repo_id UUID NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    symbol_name VARCHAR,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1024),
    -- Generated column for full-text search based on the chunk content
    content_tsvector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE TABLE dependency_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    source_file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    target_file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    edge_type VARCHAR NOT NULL
);

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    role VARCHAR NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- 4. Create Indexes

-- Index 1: HNSW index on the vector embedding.
-- Why: Allows for highly efficient approximate nearest neighbor (ANN) search 
-- to find chunks with similar semantic meaning based on cosine distance.
CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);

-- Index 2: Plain B-tree index on repo_id.
-- Why: Queries will always filter by repo first before applying vector or full-text search, 
-- ensuring we isolate operations to a specific codebase.
CREATE INDEX idx_chunks_repo_id ON chunks (repo_id);

-- Index 3: GIN index on the generated tsvector column.
-- Why: Enables fast inverted index lookups for Postgres full-text keyword search.
CREATE INDEX idx_chunks_content_tsvector ON chunks USING GIN (content_tsvector);

-- Recommended standard foreign key indices to prevent full table scans
CREATE INDEX idx_files_repo_id ON files (repo_id);
CREATE INDEX idx_dependency_edges_repo_id ON dependency_edges (repo_id);
CREATE INDEX idx_dependency_edges_source_file_id ON dependency_edges (source_file_id);
CREATE INDEX idx_dependency_edges_target_file_id ON dependency_edges (target_file_id);
CREATE INDEX idx_chat_messages_repo_id ON chat_messages (repo_id);
