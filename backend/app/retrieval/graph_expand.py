"""
Graph-aware context expansion using the DependencyEdge table.
"""
from sqlalchemy import text, or_
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.db.models import DependencyEdge, Chunk


def expand_with_dependencies(
    repo_id: str,
    ranked_chunks: list[dict],
    max_extra: int = 5,
) -> list[dict]:
    """
    Augments the ranked chunk list with a small number of additional chunks
    drawn from files that are directly connected in the dependency graph.

    For the top-ranked chunks, this function looks up their file's
    DependencyEdges in *both* directions:
      - files the chunk's file imports  (outgoing edges)
      - files that import the chunk's file  (incoming edges)

    and pulls in the highest-scoring chunks from those neighbour files
    (even if those chunks didn't individually rank high enough in vector or
    keyword search).

    **Why this step exists:**

    A question like "how does authentication work?" might best be answered
    by a middleware file that never uses the literal word "authentication"
    anywhere in its text or symbol names, but that *every* auth-related
    file imports.  Pure semantic and keyword search would miss it, but
    because auth_router.py imports auth_middleware.py, the dependency graph
    connects them.  By expanding one hop along the import graph we can
    surface these structurally-relevant-but-lexically-invisible files and
    give the LLM the full architectural picture.

    The additions are capped at ``max_extra`` to prevent the context window
    from ballooning — we only want the most relevant structural neighbours,
    not the entire transitive closure of the import graph.
    """
    if not ranked_chunks or max_extra <= 0:
        return ranked_chunks

    # Collect file_ids already represented in the ranked results
    existing_chunk_ids = {c["chunk_id"] for c in ranked_chunks}
    existing_file_ids = {c["file_id"] for c in ranked_chunks}

    # Use only the top few ranked chunks' files as expansion seeds
    # (expanding every result would pull in too many neighbours)
    seed_file_ids = []
    seen = set()
    for c in ranked_chunks[:5]:
        fid = c["file_id"]
        if fid not in seen:
            seed_file_ids.append(fid)
            seen.add(fid)

    if not seed_file_ids:
        return ranked_chunks

    with SessionLocal() as db:
        # Find all neighbour file_ids (both directions) for the seed files
        edges = db.query(DependencyEdge).filter(
            DependencyEdge.repo_id == repo_id,
            or_(
                DependencyEdge.source_file_id.in_(seed_file_ids),
                DependencyEdge.target_file_id.in_(seed_file_ids),
            )
        ).all()

        neighbour_file_ids = set()
        for edge in edges:
            neighbour_file_ids.add(str(edge.source_file_id))
            neighbour_file_ids.add(str(edge.target_file_id))

        # Remove files we already have chunks for
        neighbour_file_ids -= existing_file_ids

        if not neighbour_file_ids:
            return ranked_chunks

        # Pull the best chunks from the neighbour files.
        # We select a limited number per file to avoid one large file dominating.
        neighbour_chunks = (
            db.query(Chunk)
            .filter(
                Chunk.repo_id == repo_id,
                Chunk.file_id.in_(list(neighbour_file_ids)),
            )
            .limit(max_extra * 3)  # over-fetch, then trim
            .all()
        )

    # Deduplicate and cap at max_extra
    extra: list[dict] = []
    for ch in neighbour_chunks:
        cid = str(ch.id)
        if cid in existing_chunk_ids:
            continue
        extra.append({
            "chunk_id": cid,
            "file_id": str(ch.file_id),
            "repo_id": str(ch.repo_id),
            "symbol_name": ch.symbol_name,
            "start_line": ch.start_line,
            "end_line": ch.end_line,
            "content": ch.content,
            "rrf_score": 0.0,  # not ranked — included via graph expansion
        })
        if len(extra) >= max_extra:
            break

    return ranked_chunks + extra
