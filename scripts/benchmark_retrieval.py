"""
Benchmarking script for CodeAtlas AI Hybrid Retrieval Pipeline.

Ingests `encode/starlette` (a real, mid-sized public repository), executes 15 
natural-language queries, records latency, checks against expected ground truth 
files, and outputs a timestamped Markdown report proving the retrieval precision.

Usage: python scripts/benchmark_retrieval.py
"""
import os
import time
import uuid
import datetime
from dataclasses import dataclass
from typing import List

from backend.app.db.session import SessionLocal
from backend.app.db.models import Repo, RepoStatus
from backend.app.ingestion.pipeline import ingest_repo
from backend.app.retrieval.pipeline import retrieve


@dataclass
class TestCase:
    query: str
    expected_file: str


# 15 hand-written queries covering lexical, semantic, and structural boundaries
TEST_SUITE = [
    TestCase("Where is the main FastAPI/Starlette application class defined?", "starlette/applications.py"),
    TestCase("How are WebSocket connections handled?", "starlette/websockets.py"),
    TestCase("Where is the routing logic implemented?", "starlette/routing.py"),
    TestCase("How does the background task feature work?", "starlette/background.py"),
    TestCase("Where is the HTTP request body parsed?", "starlette/requests.py"),
    TestCase("How are responses formatted?", "starlette/responses.py"),
    TestCase("Where is the middleware base class defined?", "starlette/middleware/base.py"),
    TestCase("How is CORS handled?", "starlette/middleware/cors.py"),
    TestCase("Where are the exceptions defined?", "starlette/exceptions.py"),
    TestCase("How does the template engine integration work?", "starlette/templating.py"),
    TestCase("Where are static files served from?", "starlette/staticfiles.py"),
    TestCase("How is session middleware implemented?", "starlette/middleware/sessions.py"),
    TestCase("Where is the TestClient class?", "starlette/testclient.py"),
    TestCase("How do endpoints work?", "starlette/endpoints.py"),
    TestCase("How are forms and multipart parsing done?", "starlette/formparsers.py"),
]


def run_benchmark(repo_url: str = "https://github.com/encode/starlette"):
    print(f"=== Starting CodeAtlas AI Benchmark ===")
    print(f"Target Repository: {repo_url}\n")
    
    # We require Postgres (pgvector) and Voyage AI for this to actually run.
    # We'll use a try/except so the script prints a nice error if env isn't setup.
    try:
        import voyageai
        if not os.getenv("VOYAGE_API_KEY"):
            print("WARNING: VOYAGE_API_KEY not set. Benchmark will fail if executed.")
    except ImportError:
        pass

    db = SessionLocal()
    
    # 1. Ingest Repo
    repo_id = str(uuid.uuid4())
    print(f"1. Ingesting repository (ID: {repo_id})...")
    
    # Create DB row
    repo = Repo(id=uuid.UUID(repo_id), github_url=repo_url, name="encode/starlette", status=RepoStatus.pending)
    db.add(repo)
    db.commit()
    
    start_ingest = time.time()
    try:
        # Warning: This is a blocking call and might take a minute depending on network/Voyage
        ingest_repo(repo_url, repo_id)
    except Exception as e:
        print(f"Ingestion failed! Is Postgres running with pgvector? Error: {e}")
        return

    ingest_time = time.time() - start_ingest
    db.refresh(repo)
    
    if repo.status != RepoStatus.ready:
        print(f"Ingestion did not complete successfully. Status: {repo.status}")
        return
        
    print(f"Ingestion complete in {ingest_time:.2f}s. Indexed {repo.file_count} files.\n")
    
    # 2. Run Retrieval Queries
    print("2. Running test queries...")
    results = []
    total_latency = 0
    hits = 0
    
    for idx, test in enumerate(TEST_SUITE, 1):
        print(f"  [{idx}/{len(TEST_SUITE)}] Query: '{test.query}'")
        
        # We need the path mapping to verify hits
        # (retrieve returns file_id, we fetch paths from DB)
        start_q = time.time()
        
        try:
            chunks = retrieve(repo_id, test.query, final_k=10, graph_extra=5)
        except Exception as e:
            print(f"    Retrieval failed: {e}")
            chunks = []
            
        latency = time.time() - start_q
        total_latency += latency
        
        # Map file_ids to paths
        from backend.app.db.models import File
        file_ids = [c["file_id"] for c in chunks]
        files = db.query(File).filter(File.id.in_(file_ids)).all()
        paths = {str(f.id): f.path for f in files}
        
        retrieved_paths = [paths.get(c["file_id"], "") for c in chunks]
        
        # Check if the expected file is in the top results (graph expanded + RRF)
        is_hit = any(test.expected_file in p for p in retrieved_paths)
        if is_hit:
            hits += 1
            print(f"    ✅ Hit! (Latency: {latency:.2f}s)")
        else:
            print(f"    ❌ Miss. Expected {test.expected_file} (Latency: {latency:.2f}s)")
            
        results.append({
            "query": test.query,
            "expected": test.expected_file,
            "hit": is_hit,
            "latency": latency,
            "top_paths": list(set(retrieved_paths))[:3] # store top 3 unique paths for the report
        })

    # 3. Generate Summary
    precision = (hits / len(TEST_SUITE)) * 100
    avg_latency = total_latency / len(TEST_SUITE)
    
    report_lines = [
        "# CodeAtlas AI Retrieval Benchmark",
        "",
        f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Repository:** {repo_url}",
        f"**Files Ingested:** {repo.file_count}",
        f"**Ingestion Time:** {ingest_time:.2f}s",
        "",
        "## Summary",
        f"- **Total Queries:** {len(TEST_SUITE)}",
        f"- **Precision (Top-15):** {precision:.1f}% ({hits}/{len(TEST_SUITE)} hits)",
        f"- **Average Latency:** {avg_latency:.3f}s",
        "",
        "## Detailed Results",
        "| Status | Query | Expected File | Latency | Top Retrieved |",
        "|---|---|---|---|---|"
    ]
    
    for r in results:
        status_icon = "✅" if r["hit"] else "❌"
        top_paths_str = "<br>".join(r["top_paths"]) if r["top_paths"] else "None"
        report_lines.append(f"| {status_icon} | {r['query']} | `{r['expected']}` | {r['latency']:.2f}s | {top_paths_str} |")
        
    report = "\n".join(report_lines)
    
    # 4. Save to results folder
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = f"results/benchmark_{timestamp}.md"
    
    with open(filepath, "w") as f:
        f.write(report)
        
    print(f"\n=== Benchmark Complete ===")
    print(f"Precision: {precision:.1f}%")
    print(f"Average Latency: {avg_latency:.3f}s")
    print(f"Report saved to: {filepath}")

if __name__ == "__main__":
    run_benchmark()
