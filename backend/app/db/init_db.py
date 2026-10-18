"""
Idempotent schema bootstrap.

Runs on FastAPI startup so a fresh Supabase / Postgres database works without
manually executing ``alembic/01_init_schema.sql``. Safe to run on every boot:
every statement is IF NOT EXISTS / checkfirst.
"""
import logging

from sqlalchemy import text

from backend.app.db.models import Base
from backend.app.db.session import engine

logger = logging.getLogger(__name__)

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_repo_id ON chunks (repo_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_content_tsvector ON chunks USING GIN (content_tsvector)",
    "CREATE INDEX IF NOT EXISTS idx_files_repo_id ON files (repo_id)",
    "CREATE INDEX IF NOT EXISTS idx_dependency_edges_repo_id ON dependency_edges (repo_id)",
    "CREATE INDEX IF NOT EXISTS idx_dependency_edges_source_file_id ON dependency_edges (source_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_dependency_edges_target_file_id ON dependency_edges (target_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_repo_id ON chat_messages (repo_id)",
]


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine, checkfirst=True)

    with engine.begin() as conn:
        # Columns added after the original SQL schema was written
        conn.execute(text("ALTER TABLE files ADD COLUMN IF NOT EXISTS content TEXT"))
        conn.execute(text("ALTER TABLE repos ADD COLUMN IF NOT EXISTS error_message TEXT"))
        for stmt in _INDEXES:
            conn.execute(text(stmt))

    logger.info("Database schema verified.")
