"""
Full-text keyword search using Postgres tsvector/tsquery and ts_rank.
"""
from sqlalchemy import text
from backend.app.db.session import SessionLocal


def keyword_search(repo_id: str, query_text: str, top_k: int = 15) -> list[dict]:
    """
    Runs a Postgres full-text search (ts_rank against the content_tsvector column)
    filtered to a specific repo_id, returning the top_k chunks by rank score.

    This catches exact identifier matches (function names, variable names, class names)
    that semantic vector similarity can miss — e.g. searching for "getUserById" will
    rank a chunk containing that exact function name highly, even if the embedding
    space doesn't place it near the query.

    Each returned dict contains:
      - chunk_id (str)
      - file_id (str)
      - repo_id (str)
      - symbol_name (str | None)
      - start_line (int)
      - end_line (int)
      - content (str)
      - score (float): ts_rank score, higher is better
    """
    # plainto_tsquery handles user input safely (splits on whitespace, joins with &).
    # ts_rank scores how well the document matches the query.
    query = text("""
        SELECT
            id,
            file_id,
            repo_id,
            symbol_name,
            start_line,
            end_line,
            content,
            ts_rank(content_tsvector, plainto_tsquery('english', :query_text)) AS score
        FROM chunks
        WHERE repo_id = :repo_id
          AND content_tsvector @@ plainto_tsquery('english', :query_text)
        ORDER BY score DESC
        LIMIT :top_k
    """)

    with SessionLocal() as db:
        rows = db.execute(query, {
            "repo_id": repo_id,
            "query_text": query_text,
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
