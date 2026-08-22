"""
Ingestion pipeline for processing and indexing repositories.
"""
import os
import uuid
import shutil
import tempfile
import logging
from collections import Counter
from typing import List, Dict, Any

from backend.app.db.session import SessionLocal
from backend.app.db.models import Repo, RepoStatus, File, Chunk
from backend.app.ingestion.github_fetch import clone_repo
from backend.app.ingestion.file_walker import list_source_files
from backend.app.ingestion.chunker import chunk_file
from backend.app.ingestion.dependency_graph import build_dependency_graph
from backend.app.ingestion.embedder import embed_chunks

logger = logging.getLogger(__name__)

DB_BATCH_SIZE = 500


def ingest_repo(github_url: str, repo_id: str):
    """
    Full repository ingestion pipeline:
    1. Update repo status to 'ingesting'.
    2. Clone repo to temporary directory (shallow clone).
    3. Walk and identify valid source files.
    4. Read contents and chunk each file with AST-aware tree-sitter chunker.
    5. Save File records to Supabase.
    6. Build dependency graph and write DependencyEdge records.
    7. Generate vector embeddings for all chunks via Voyage AI (voyage-code-3).
    8. Write Chunk records with embeddings to Supabase in batches.
    9. Update repo status to 'ready' and record file count.
    
    If any error occurs, catches the exception, updates repo status to 'failed',
    and logs the error.
    """
    repo_uuid = uuid.UUID(repo_id) if isinstance(repo_id, str) else repo_id
    logger.info(f"Starting ingestion pipeline for repo {repo_uuid} ({github_url})")

    # Update repo status to 'ingesting'
    with SessionLocal() as db:
        repo = db.query(Repo).filter(Repo.id == repo_uuid).first()
        if repo:
            repo.status = RepoStatus.ingesting
            db.commit()

    temp_dir = tempfile.mkdtemp(prefix=f"repo_{repo_uuid}_")

    try:
        # Step 1: Clone repository
        logger.info(f"Cloning {github_url} into {temp_dir}...")
        clone_repo(github_url, temp_dir)

        # Step 2: Walk source files
        source_files = list_source_files(temp_dir)
        logger.info(f"Found {len(source_files)} source files in {github_url}")

        if not source_files:
            logger.warning(f"No valid source files found for repo {repo_uuid}")
            with SessionLocal() as db:
                repo = db.query(Repo).filter(Repo.id == repo_uuid).first()
                if repo:
                    repo.status = RepoStatus.ready
                    repo.file_count = 0
                    db.commit()
            return

        # Step 3: Read file contents and prepare File entities + Chunks
        files_data: List[Dict[str, Any]] = []
        all_chunk_metadata: List[Dict[str, Any]] = []

        for file_info in source_files:
            rel_path = file_info["path"]
            lang = file_info["language"]
            abs_path = os.path.join(temp_dir, rel_path)

            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception as read_err:
                logger.warning(f"Failed to read file {rel_path}: {read_err}")
                continue

            file_id = uuid.uuid4()
            file_record = {
                "id": file_id,
                "path": rel_path,
                "language": lang,
                "content": content
            }
            files_data.append(file_record)

            # Chunk file
            file_chunks = chunk_file(rel_path, content, lang)
            for ch in file_chunks:
                all_chunk_metadata.append({
                    "id": uuid.uuid4(),
                    "file_id": file_id,
                    "repo_id": repo_uuid,
                    "symbol_name": ch.get("symbol_name"),
                    "start_line": ch["start_line"],
                    "end_line": ch["end_line"],
                    "content": ch["content"]
                })

        # Step 4: Write File rows to database in batches
        with SessionLocal() as db:
            file_models = [
                File(
                    id=f["id"],
                    repo_id=repo_uuid,
                    path=f["path"],
                    language=f["language"]
                )
                for f in files_data
            ]
            for i in range(0, len(file_models), DB_BATCH_SIZE):
                db.add_all(file_models[i : i + DB_BATCH_SIZE])
                db.commit()

        logger.info(f"Persisted {len(files_data)} File rows to database")

        # Step 5: Build dependency graph (creates and commits DependencyEdges)
        logger.info(f"Building dependency graph for {len(files_data)} files...")
        build_dependency_graph(str(repo_uuid), files_data)

        # Step 6: Generate embeddings for all chunks via Voyage AI
        if all_chunk_metadata:
            logger.info(f"Generating embeddings for {len(all_chunk_metadata)} chunks with Voyage AI (voyage-code-3)...")
            embeddings = embed_chunks(all_chunk_metadata)

            # Step 7: Write Chunk rows (with embeddings) to database in batches
            logger.info(f"Persisting {len(all_chunk_metadata)} Chunk rows to database...")
            with SessionLocal() as db:
                chunk_models = [
                    Chunk(
                        id=ch["id"],
                        file_id=ch["file_id"],
                        repo_id=ch["repo_id"],
                        symbol_name=ch["symbol_name"],
                        start_line=ch["start_line"],
                        end_line=ch["end_line"],
                        content=ch["content"],
                        embedding=embeddings[idx] if idx < len(embeddings) else None
                    )
                    for idx, ch in enumerate(all_chunk_metadata)
                ]

                for i in range(0, len(chunk_models), DB_BATCH_SIZE):
                    db.add_all(chunk_models[i : i + DB_BATCH_SIZE])
                    db.commit()

        # Step 8: Mark repo as ready with total file count
        with SessionLocal() as db:
            repo = db.query(Repo).filter(Repo.id == repo_uuid).first()
            if repo:
                repo.status = RepoStatus.ready
                repo.file_count = len(files_data)
                db.commit()

        logger.info(f"Successfully finished ingestion for repo {repo_uuid}: {len(files_data)} files, {len(all_chunk_metadata)} chunks")

    except Exception as e:
        logger.exception(f"Ingestion failed for repo {repo_uuid} ({github_url}): {e}")
        try:
            with SessionLocal() as db:
                repo = db.query(Repo).filter(Repo.id == repo_uuid).first()
                if repo:
                    repo.status = RepoStatus.failed
                    db.commit()
        except Exception as db_err:
            logger.error(f"Failed to update repo status to failed: {db_err}")
    finally:
        # Cleanup cloned directory
        shutil.rmtree(temp_dir, ignore_errors=True)
