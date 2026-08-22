"""
Vector similarity search using pgvector cosine distance.
"""
from sqlalchemy import text
from backend.app.db.session import SessionLocal


def vector_search(repo_id: str, query_embedding: list[float], top_k: int = 15) -> list[dict]:
    """
    Runs a pgvector cosine-distance similarity query against Chunk.embedding,
    filtered to a specific repo_id, returning the top_k closest chunks.

    Each returned dict contains:
      - chunk_id (str)
      - file_id (str)
      - repo_id (str)
      - symbol_name (str | None)
      - start_line (int)
      - end_line (int)
      - content (str)
      - score (float): cosine similarity (1 - cosine_distance), higher is better
    """
    # pgvector's <=> operator computes cosine distance (0 = identical, 2 = opposite).
    # We convert to similarity by subtracting from 1.
    query = text("""
        SELECT
            id,
            file_id,
            repo_id,
            symbol_name,
            start_line,
            end_line,
            content,
            1 - (embedding <=> :embedding::vector) AS score
        FROM chunks
        WHERE repo_id = :repo_id
          AND embedding IS NOT NULL
        ORDER BY embedding <=> :embedding::vector ASC
        LIMIT :top_k
    """)

    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    with SessionLocal() as db:
        rows = db.execute(query, {
            "repo_id": repo_id,
            "embedding": embedding_str,
            "top_k": top_k,
        }).fetchall()

    return [
        {
            "chunk_id": str(row.id),
            "file_id": str(row.file_id),
            "repo_id": str(row.repo_id),
            "symbol_name": row.symbol_name,
            "start_line": row.start_line,
            "end_line": row.end_line,
            "content": row.content,
            "score": float(row.score),
        }
        for row in rows
    ]
