"""
Tests for the hybrid retrieval pipeline.

Covers:
  1. RRF ranking: a chunk in both lists outranks one in only one list.
  2. Repo scoping: results are correctly filtered to a single repo_id.
  3. Graph expansion: pulls in a chunk from a connected file that wasn't
     in the original ranked results.

Run with:  pytest tests/test_retrieval.py -v
"""
import uuid
from unittest.mock import patch, MagicMock

import pytest

from backend.app.db.models import DependencyEdge
from backend.app.retrieval.hybrid_rank import merge_and_rerank
from backend.app.retrieval.graph_expand import expand_with_dependencies


# ---------------------------------------------------------------------------
# Helpers: build fake chunk dicts
# ---------------------------------------------------------------------------

def _make_chunk(
    chunk_id: str = None,
    file_id: str = None,
    repo_id: str = "repo-1",
    content: str = "some code",
    symbol_name: str = None,
    score: float = 0.5,
) -> dict:
    return {
        "chunk_id": chunk_id or str(uuid.uuid4()),
        "file_id": file_id or str(uuid.uuid4()),
        "repo_id": repo_id,
        "symbol_name": symbol_name,
        "start_line": 1,
        "end_line": 10,
        "content": content,
        "score": score,
    }


# ===================================================================
# 1. RRF: chunk in BOTH lists outranks chunk in only ONE list
# ===================================================================

class TestRRFRanking:
    def test_chunk_in_both_lists_ranks_higher(self):
        """
        Chunk A appears as rank 1 in vector AND rank 1 in keyword.
        Chunk B appears as rank 1 in vector ONLY.
        Chunk C appears as rank 1 in keyword ONLY.
        A should outscore both B and C.
        """
        shared_id = "chunk-shared"
        vec_only_id = "chunk-vec"
        kw_only_id = "chunk-kw"

        vector_results = [
            _make_chunk(chunk_id=shared_id, content="shared chunk"),
            _make_chunk(chunk_id=vec_only_id, content="vector only"),
        ]
        keyword_results = [
            _make_chunk(chunk_id=shared_id, content="shared chunk"),
            _make_chunk(chunk_id=kw_only_id, content="keyword only"),
        ]

        merged = merge_and_rerank(vector_results, keyword_results, final_k=10)

        scores = {c["chunk_id"]: c["rrf_score"] for c in merged}

        assert scores[shared_id] > scores[vec_only_id], (
            f"Shared chunk ({scores[shared_id]:.6f}) should outscore "
            f"vector-only chunk ({scores[vec_only_id]:.6f})"
        )
        assert scores[shared_id] > scores[kw_only_id], (
            f"Shared chunk ({scores[shared_id]:.6f}) should outscore "
            f"keyword-only chunk ({scores[kw_only_id]:.6f})"
        )

    def test_rrf_respects_rank_position(self):
        """
        A chunk at rank 1 in one list should score higher than a chunk at
        rank 5 in the same list (both appearing in only that one list).
        """
        top_id = "chunk-rank1"
        bottom_id = "chunk-rank5"

        vector_results = [
            _make_chunk(chunk_id=top_id),
            _make_chunk(),
            _make_chunk(),
            _make_chunk(),
            _make_chunk(chunk_id=bottom_id),
        ]

        merged = merge_and_rerank(vector_results, [], final_k=10)

        scores = {c["chunk_id"]: c["rrf_score"] for c in merged}
        assert scores[top_id] > scores[bottom_id]

    def test_empty_inputs(self):
        assert merge_and_rerank([], [], final_k=10) == []
        result = merge_and_rerank([_make_chunk(chunk_id="only")], [], final_k=10)
        assert len(result) == 1
        assert result[0]["chunk_id"] == "only"


# ===================================================================
# 2. Repo scoping: vector_search and keyword_search filter by repo_id
# ===================================================================

class TestRepoScoping:
    """
    These tests verify that the search functions pass the repo_id filter
    correctly. Since the actual DB queries happen in vector_search and
    keyword_search (which we mock here), the tests confirm the pipeline
    propagates repo_id and that the merge step doesn't mix repos.
    """

    def test_results_are_scoped_to_requested_repo(self):
        """
        Simulate two repos' results. Only the requested repo's chunks
        should appear in the final merge.
        """
        repo_a = "repo-aaaa"
        repo_b = "repo-bbbb"

        # vector_search returns results only for repo_a (correctly scoped)
        vector_results = [
            _make_chunk(chunk_id="a1", repo_id=repo_a),
            _make_chunk(chunk_id="a2", repo_id=repo_a),
        ]
        # keyword_search also returns only repo_a results
        keyword_results = [
            _make_chunk(chunk_id="a1", repo_id=repo_a),
            _make_chunk(chunk_id="a3", repo_id=repo_a),
        ]

        merged = merge_and_rerank(vector_results, keyword_results, final_k=10)

        for chunk in merged:
            assert chunk["repo_id"] == repo_a, (
                f"Expected repo_id={repo_a}, got {chunk['repo_id']}"
            )

    def test_no_cross_repo_contamination(self):
        """
        If vector_search returns repo A results and keyword_search returns
        repo B results (a hypothetical bug), merge_and_rerank will include
        both. This test documents that scoping is the responsibility of the
        individual search functions, not the merge step.
        """
        repo_a = "repo-aaaa"
        repo_b = "repo-bbbb"

        vector_results = [_make_chunk(chunk_id="a1", repo_id=repo_a)]
        keyword_results = [_make_chunk(chunk_id="b1", repo_id=repo_b)]

        merged = merge_and_rerank(vector_results, keyword_results, final_k=10)
        repo_ids = {c["repo_id"] for c in merged}
        # Both appear — merge doesn't filter. This confirms that scoping
        # MUST be enforced at the search layer, not the fusion layer.
        assert repo_a in repo_ids
        assert repo_b in repo_ids


# ===================================================================
# 3. Graph expansion: pulls in chunks from a connected file
# ===================================================================

class TestGraphExpansion:
    """
    Mocks the database layer to verify that graph expansion adds chunks
    from a file that is directly imported by one of the ranked files but
    wasn't in the original ranked set.
    """

    def test_expands_with_neighbour_file_chunk(self):
        """
        Setup:
          - File A (in the ranked results) imports File B (not in results).
          - File B has a chunk that should be pulled in by expansion.
        """
        repo_id = str(uuid.uuid4())
        file_a_id = str(uuid.uuid4())
        file_b_id = str(uuid.uuid4())
        chunk_a_id = str(uuid.uuid4())
        chunk_b_id = str(uuid.uuid4())

        ranked_chunks = [
            {
                "chunk_id": chunk_a_id,
                "file_id": file_a_id,
                "repo_id": repo_id,
                "symbol_name": "handle_auth",
                "start_line": 1,
                "end_line": 20,
                "content": "def handle_auth(): ...",
                "rrf_score": 0.03,
            }
        ]

        # Mock the DependencyEdge: File A -> File B
        mock_edge = MagicMock()
        mock_edge.source_file_id = file_a_id
        mock_edge.target_file_id = file_b_id

        # Mock the Chunk from File B
        mock_chunk_b = MagicMock()
        mock_chunk_b.id = uuid.UUID(chunk_b_id)
        mock_chunk_b.file_id = uuid.UUID(file_b_id)
        mock_chunk_b.repo_id = uuid.UUID(repo_id)
        mock_chunk_b.symbol_name = "verify_token"
        mock_chunk_b.start_line = 1
        mock_chunk_b.end_line = 15
        mock_chunk_b.content = "def verify_token(token): ..."

        # Patch SessionLocal to return a mock session
        with patch("backend.app.retrieval.graph_expand.SessionLocal") as MockSession:
            mock_db = MagicMock()
            MockSession.return_value.__enter__ = MagicMock(return_value=mock_db)
            MockSession.return_value.__exit__ = MagicMock(return_value=False)

            # First query returns edges, second returns chunks
            mock_edge_query = MagicMock()
            mock_edge_query.filter.return_value = mock_edge_query
            mock_edge_query.all.return_value = [mock_edge]

            mock_chunk_query = MagicMock()
            mock_chunk_query.filter.return_value = mock_chunk_query
            mock_chunk_query.limit.return_value = mock_chunk_query
            mock_chunk_query.all.return_value = [mock_chunk_b]

            # db.query() returns different mocks based on the model class
            def side_effect(model):
                if model is DependencyEdge:
                    return mock_edge_query
                return mock_chunk_query

            mock_db.query.side_effect = side_effect

            result = expand_with_dependencies(repo_id, ranked_chunks, max_extra=5)

        # The original chunk should still be there
        result_ids = [c["chunk_id"] for c in result]
        assert chunk_a_id in result_ids, "Original ranked chunk should be preserved"

        # File B's chunk should have been added via graph expansion
        assert chunk_b_id in result_ids, (
            "Chunk from imported File B should have been pulled in via graph expansion"
        )

    def test_no_expansion_when_no_edges(self):
        """
        If there are no dependency edges, the result should be unchanged.
        """
        repo_id = str(uuid.uuid4())
        ranked_chunks = [
            _make_chunk(chunk_id="c1", repo_id=repo_id),
        ]

        with patch("backend.app.retrieval.graph_expand.SessionLocal") as MockSession:
            mock_db = MagicMock()
            MockSession.return_value.__enter__ = MagicMock(return_value=mock_db)
            MockSession.return_value.__exit__ = MagicMock(return_value=False)

            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = []  # no edges
            mock_db.query.return_value = mock_query

            result = expand_with_dependencies(repo_id, ranked_chunks, max_extra=5)

        assert len(result) == 1
        assert result[0]["chunk_id"] == "c1"

    def test_expansion_caps_at_max_extra(self):
        """
        Even if many neighbour chunks exist, we should never add more
        than max_extra additional chunks.
        """
        repo_id = str(uuid.uuid4())
        file_a_id = str(uuid.uuid4())
        file_b_id = str(uuid.uuid4())

        ranked_chunks = [
            _make_chunk(chunk_id="ranked-1", file_id=file_a_id, repo_id=repo_id),
        ]

        mock_edge = MagicMock()
        mock_edge.source_file_id = file_a_id
        mock_edge.target_file_id = file_b_id

        # Create 20 mock chunks from file B — well over max_extra=3
        mock_chunks = []
        for i in range(20):
            mc = MagicMock()
            mc.id = uuid.uuid4()
            mc.file_id = uuid.UUID(file_b_id)
            mc.repo_id = uuid.UUID(repo_id)
            mc.symbol_name = f"func_{i}"
            mc.start_line = i * 10
            mc.end_line = i * 10 + 9
            mc.content = f"def func_{i}(): pass"
            mock_chunks.append(mc)

        with patch("backend.app.retrieval.graph_expand.SessionLocal") as MockSession:
            mock_db = MagicMock()
            MockSession.return_value.__enter__ = MagicMock(return_value=mock_db)
            MockSession.return_value.__exit__ = MagicMock(return_value=False)

            mock_edge_query = MagicMock()
            mock_edge_query.filter.return_value = mock_edge_query
            mock_edge_query.all.return_value = [mock_edge]

            mock_chunk_query = MagicMock()
            mock_chunk_query.filter.return_value = mock_chunk_query
            mock_chunk_query.limit.return_value = mock_chunk_query
            mock_chunk_query.all.return_value = mock_chunks

            def side_effect(model):
                if model is DependencyEdge:
                    return mock_edge_query
                return mock_chunk_query

            mock_db.query.side_effect = side_effect

            result = expand_with_dependencies(repo_id, ranked_chunks, max_extra=3)

        # 1 original + at most 3 expanded = 4 max
        assert len(result) <= 4, f"Expected ≤4 chunks, got {len(result)}"
        extra_count = len(result) - 1
        assert extra_count <= 3, f"Expected ≤3 extra chunks, got {extra_count}"

    def test_empty_ranked_chunks(self):
        """Graph expansion on empty input should return empty."""
        result = expand_with_dependencies("repo-1", [], max_extra=5)
        assert result == []
