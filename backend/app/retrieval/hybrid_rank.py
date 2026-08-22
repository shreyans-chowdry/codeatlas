"""
Reciprocal Rank Fusion (RRF) for combining vector and keyword search results.
"""
from collections import defaultdict

# RRF smoothing constant (standard value from the original Cormack et al. paper).
# Prevents the top-ranked item from having disproportionate influence.
RRF_K = 60


def merge_and_rerank(
    vector_results: list[dict],
    keyword_results: list[dict],
    final_k: int = 10,
) -> list[dict]:
    """
    Combines vector search and keyword search results using Reciprocal Rank Fusion.

    For each chunk, the RRF score is:

        score = Σ  1 / (K + rank_i)

    where rank_i is the 1-based position in each list the chunk appears in,
    and K is a smoothing constant (60).  A chunk appearing in BOTH lists
    accumulates contributions from both, so it will generally outscore a
    chunk appearing in only one list.

    **Why RRF instead of averaging raw scores?**

    Vector cosine similarity and Postgres ts_rank scores live on completely
    different, incomparable scales — cosine similarity ranges roughly 0–1
    while ts_rank can be any non-negative float whose magnitude depends on
    document length and term frequency.  Normalising them into a common
    range is fragile and distribution-dependent.  RRF sidesteps the problem
    entirely by only caring about **rank position** within each result list,
    not the raw score values.  This makes the fusion robust regardless of
    how the individual scorers are calibrated.
    """
    # Map chunk_id -> full chunk dict (keep the first occurrence seen)
    chunk_map: dict[str, dict] = {}
    # Map chunk_id -> cumulative RRF score
    rrf_scores: dict[str, float] = defaultdict(float)

    for rank, chunk in enumerate(vector_results, start=1):
        cid = chunk["chunk_id"]
        rrf_scores[cid] += 1.0 / (RRF_K + rank)
        if cid not in chunk_map:
            chunk_map[cid] = chunk

    for rank, chunk in enumerate(keyword_results, start=1):
        cid = chunk["chunk_id"]
        rrf_scores[cid] += 1.0 / (RRF_K + rank)
        if cid not in chunk_map:
            chunk_map[cid] = chunk

    # Sort by combined RRF score descending
    sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)

    results = []
    for cid in sorted_ids[:final_k]:
        entry = dict(chunk_map[cid])  # shallow copy
        entry["rrf_score"] = rrf_scores[cid]
        results.append(entry)

    return results
