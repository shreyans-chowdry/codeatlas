"""
Chat endpoint for CodeAtlas AI.

POST /repos/{repo_id}/chat
  - Accepts a question.
  - Retrieves relevant code chunks using the hybrid retrieval pipeline.
  - Streams the Claude response back as SSE (server-sent events).
  - Persists both the user message and the full assistant reply to the DB.
"""
import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db.session import get_db, SessionLocal
from backend.app.db.models import Repo, RepoStatus, File, ChatMessage
from backend.app.retrieval.pipeline import retrieve
from backend.app.llm.claude_client import stream_answer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repos", tags=["chat"])


class ChatRequest(BaseModel):
    question: str


def _enrich_chunks_with_paths(chunks: list[dict], db: Session) -> list[dict]:
    """
    The retrieval layer returns 'file_id' for each chunk but not the file path.
    This resolves all unique file_ids in one DB round-trip and annotates each
    chunk with its 'file_path' so the prompt builder can label them correctly.
    """
    unique_file_ids = list({c["file_id"] for c in chunks})
    files = db.query(File).filter(File.id.in_(unique_file_ids)).all()
    path_by_id = {str(f.id): f.path for f in files}

    enriched = []
    for chunk in chunks:
        enriched.append({**chunk, "file_path": path_by_id.get(chunk["file_id"], "unknown")})
    return enriched


def _persist_assistant_message(repo_id: uuid.UUID, accumulated: list[str]) -> None:
    """
    BackgroundTask that persists the assistant ChatMessage after streaming.

    **Why a BackgroundTask instead of a finally block in the generator?**

    FastAPI propagates asyncio.CancelledError into the generator when a client
    disconnects mid-stream. Whether `finally` runs reliably depends on the
    HTTP transport and how the Anthropic SDK cleans up its own async context
    manager — in practice it is NOT guaranteed. BackgroundTasks run in the
    same event loop but *after* the Response is fully sent (or abandoned),
    so they are decoupled from the SSE stream lifecycle and survive disconnects.
    Even if the client closed the tab after receiving only 3 tokens, the
    partial text accumulated so far is written to the DB.
    """
    full_response = "".join(accumulated)
    if not full_response:
        return
    try:
        with SessionLocal() as db:
            db.add(ChatMessage(repo_id=repo_id, role="assistant", content=full_response))
            db.commit()
    except Exception as exc:
        logger.error(f"Failed to persist assistant ChatMessage for repo {repo_id}: {exc}")


async def _generate_sse_stream(
    repo_id: uuid.UUID,
    question: str,
    chunks: list[dict],
    accumulated: list[str],
) -> AsyncGenerator[str, None]:
    """
    Streams Claude's response token-by-token as SSE events.
    Appends each delta to `accumulated` (a shared mutable list) so the
    BackgroundTask can persist it after the stream ends — even if the
    client disconnects before the stream completes.
    """
    try:
        async for text_delta in stream_answer(question, chunks):
            accumulated.append(text_delta)
            # SSE format: "data: <payload>\n\n"
            payload = json.dumps({"type": "delta", "text": text_delta})
            yield f"data: {payload}\n\n"

        # Signal that the stream is complete
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as exc:
        logger.exception(f"Error streaming Claude response for repo {repo_id}: {exc}")
        error_payload = json.dumps({"type": "error", "message": "An error occurred while generating the response."})
        yield f"data: {error_payload}\n\n"


async def _no_context_sse_stream(message: str) -> AsyncGenerator[str, None]:
    """
    Yields a single SSE event with a clear 'no context' explanation,
    then signals done. Used when retrieval returns zero chunks so we
    never send an empty-context prompt to the LLM.
    """
    payload = json.dumps({"type": "delta", "text": message})
    yield f"data: {payload}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/{repo_id}/chat")
async def chat(
    repo_id: uuid.UUID,
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    POST /repos/{repo_id}/chat

    Accepts a natural-language question, retrieves relevant code context,
    and streams Claude's answer back as server-sent events.

    SSE event shapes:
      data: {"type": "delta", "text": "<streamed text>"}
      data: {"type": "done"}
      data: {"type": "error", "message": "<error message>"}
    """
    # Validate repo exists
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found.")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    # Persist user message immediately (before streaming starts)
    user_msg = ChatMessage(
        repo_id=repo_id,
        role="user",
        content=question,
    )
    db.add(user_msg)
    db.commit()

    # Guard: repo must be ready before we attempt retrieval
    if repo.status != RepoStatus.ready:
        no_context_message = (
            f"This repository is currently in '{repo.status.value}' status and has not "
            "finished ingestion yet. Please try again once ingestion is complete."
        )
        return StreamingResponse(
            _no_context_sse_stream(no_context_message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Run synchronous retrieval (runs Voyage AI + DB queries in thread pool internally)
    try:
        raw_chunks = retrieve(str(repo_id), question)
    except Exception as exc:
        logger.exception(f"Retrieval failed for repo {repo_id}: {exc}")
        raise HTTPException(status_code=500, detail="Retrieval failed. Please try again.")

    # Guard: zero chunks means we have no context to ground the answer
    if not raw_chunks:
        no_context_message = (
            "No relevant code was found for your question in this repository. "
            "This may mean the repository doesn't contain code related to your query, "
            "or that ingestion has not yet completed. Please rephrase your question or "
            "check the repository status."
        )
        return StreamingResponse(
            _no_context_sse_stream(no_context_message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Enrich chunks with their human-readable file paths for prompt labeling
    chunks = _enrich_chunks_with_paths(raw_chunks, db)

    # Shared mutable list: the generator appends deltas, the BackgroundTask reads them.
    # This decouples persistence from the stream lifecycle so it survives disconnects.
    accumulated: list[str] = []
    background_tasks.add_task(_persist_assistant_message, repo_id, accumulated)

    return StreamingResponse(
        _generate_sse_stream(repo_id, question, chunks, accumulated),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
