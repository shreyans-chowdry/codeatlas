"""
Top-level retrieval orchestrator.

Ties together vector search, keyword search, hybrid RRF re-ranking,
and graph-based context expansion into a single ``retrieve()`` call.
"""
import os
import logging
from concurrent.futures import ThreadPoolExecutor

import voyageai

from backend.app.retrieval.vector_search import vector_search
from backend.app.retrieval.keyword_search import keyword_search
from backend.app.retrieval.hybrid_rank import merge_and_rerank
from backend.app.retrieval.graph_expand import expand_with_dependencies

logger = logging.getLogger(__name__)

VOYAGE_MODEL = "voyage-code-3"


def _embed_query(query_text: str) -> list[float]:
    """
    Embeds the user query using Voyage AI with input_type="query".
    (Voyage distinguishes document vs. query embeddings for asymmetric retrieval.)
    """
    client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    result = client.embed(
        texts=[query_text],
        model=VOYAGE_MODEL,
        input_type="query",
    )
    return result.embeddings[0]


def retrieve(
    repo_id: str,
    query_text: str,
    vector_top_k: int = 15,
    keyword_top_k: int = 15,
    final_k: int = 10,
    graph_extra: int = 5,
) -> list[dict]:
    """
    Full hybrid retrieval pipeline:

    1. Embed the query with Voyage AI (input_type="query").
    2. Run vector_search and keyword_search **in parallel**.
    3. Merge both result sets with Reciprocal Rank Fusion.
    4. Expand the top results along the dependency graph.
    5. Return the final chunk list ready for the LLM context window.
    """
    # Step 1: embed the query
    query_embedding = _embed_query(query_text)

    # Step 2: run both searches in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        vec_future = pool.submit(vector_search, repo_id, query_embedding, vector_top_k)
        kw_future = pool.submit(keyword_search, repo_id, query_text, keyword_top_k)

        vector_results = vec_future.result()
        keyword_results = kw_future.result()

    logger.info(
        f"Retrieval for repo {repo_id}: "
        f"{len(vector_results)} vector hits, {len(keyword_results)} keyword hits"
    )

    # Step 3: merge & re-rank with RRF
    ranked = merge_and_rerank(vector_results, keyword_results, final_k=final_k)

    # Step 4: graph expansion
    expanded = expand_with_dependencies(repo_id, ranked, max_extra=graph_extra)

    logger.info(
        f"Final retrieval: {len(ranked)} ranked + "
        f"{len(expanded) - len(ranked)} graph-expanded = {len(expanded)} total chunks"
    )

    return expanded
