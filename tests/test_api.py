"""
API tests for CodeAtlas AI.

Covers:
- POST /repos with a valid GitHub URL (returns 200, status "pending")
- POST /repos with a malformed URL (returns 400/422)
- GET /repos/{id}/status transitions
- POST /repos/{id}/chat guard (prevents querying an un-ingested repo)
"""
import uuid
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.db.models import Repo, RepoStatus
from backend.app.db.session import get_db

client = TestClient(app)

# We use an in-memory or transactional DB for real tests, 
# but for these API tests we can just mock the DB session 
# or use the real one if it's connected to a test DB.
# For simplicity and since we don't have a test Postgres instance 
# with pgvector running, we'll mock the DB session via dependency override.

@pytest.fixture(scope="function")
def mock_db():
    mock_session = MagicMock()
    # Override get_db in FastAPI app
    app.dependency_overrides[get_db] = lambda: mock_session
    yield mock_session
    # Clean up
    app.dependency_overrides.clear()


def test_post_repos_valid_url(mock_db):
    """
    POST /repos with a valid GitHub URL should return 200, 
    a repo_id, and status="pending".
    We mock the background task to prevent actual ingestion during the test.
    """
    # When creating a Repo, SQLAlchemy adds an auto-generated id. 
    # We simulate this behavior for the mock.
    def mock_add(obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

    mock_db.add.side_effect = mock_add
    # No previously-indexed copy of this repo exists
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    
    with patch("backend.app.routers.repos.BackgroundTasks.add_task") as mock_add_task:
        response = client.post("/repos/", json={"github_url": "https://github.com/tiangolo/fastapi"})
        
        assert response.status_code == 200
        data = response.json()
        assert "repo_id" in data
        assert data["status"] == "pending"
        
        # Verify background task was queued
        assert mock_add_task.called


def test_post_repos_invalid_url():
    """
    POST /repos with a malformed URL should return 400.
    """
    response = client.post("/repos/", json={"github_url": "https://gitlab.com/some/repo"})
    assert response.status_code == 400
    assert "Must be a valid github.com URL" in response.json()["detail"]


def test_get_repo_status(mock_db):
    """
    GET /repos/{id}/status should accurately return the DB status.
    """
    dummy_id = uuid.uuid4()
    
    # Configure mock query to return a specific Repo
    mock_repo = Repo(
        id=dummy_id,
        github_url="https://github.com/dummy/repo",
        name="dummy/repo",
        status=RepoStatus.ingesting,
        file_count=42
    )
    
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = mock_repo
    mock_db.query.return_value = mock_query

    # 1. Fetch status
    response = client.get(f"/repos/{str(dummy_id)}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ingesting"
    assert data["file_count"] == 42
    
    # 2. Test non-existent repo
    mock_query.first.return_value = None
    bad_res = client.get(f"/repos/{str(uuid.uuid4())}/status")
    assert bad_res.status_code == 404
    
    # 3. Test invalid UUID format
    invalid_res = client.get("/repos/not-a-uuid/status")
    assert invalid_res.status_code == 400


def test_post_chat_unready_repo_guard(mock_db):
    """
    POST /repos/{id}/chat before a repo is "ready" returns a clear error
    stream instead of silently querying an empty index.
    """
    dummy_id = uuid.uuid4()
    
    # Mock query to return a 'pending' repo
    mock_repo = Repo(
        id=dummy_id,
        github_url="https://github.com/dummy/repo",
        name="dummy/repo",
        status=RepoStatus.pending
    )
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = mock_repo
    mock_db.query.return_value = mock_query

    # Attempt to chat
    response = client.post(
        f"/repos/{str(dummy_id)}/chat", 
        json={"question": "Where is the router?"}
    )
    
    assert response.status_code == 200
    
    # It should return an SSE stream. Let's read the text.
    stream_text = response.text
    assert 'data: {"type": "delta", "text": "This repository is currently in \'pending\' status' in stream_text
    assert 'data: {"type": "done"}' in stream_text


@pytest.mark.parametrize("raw", [
    "https://github.com/pallets/flask",
    "github.com/pallets/flask",
    "https://github.com/pallets/flask.git",
    "https://github.com/pallets/flask/",
    "https://github.com/pallets/flask/tree/main/src",
])
def test_github_url_normalization(raw):
    from backend.app.routers.repos import normalize_github_url
    assert normalize_github_url(raw) == ("https://github.com/pallets/flask", "pallets/flask")


def test_reuses_existing_index(mock_db):
    """Submitting a URL that is already indexed returns the existing repo instead of re-ingesting."""
    existing = Repo(id=uuid.uuid4(), github_url="https://github.com/pallets/flask", name="pallets/flask", status=RepoStatus.ready)
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = existing
    with patch("backend.app.routers.repos.BackgroundTasks.add_task") as mock_add_task:
        res = client.post("/repos", json={"github_url": "https://github.com/pallets/flask.git"})
    assert res.status_code == 200
    assert res.json() == {"repo_id": str(existing.id), "status": "ready", "reused": True}
    assert not mock_add_task.called
