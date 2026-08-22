from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.app.db.session import get_db
from backend.app.db.models import Repo, RepoStatus
from backend.app.ingestion.pipeline import ingest_repo

router = APIRouter(prefix="/repos", tags=["repos"])

class RepoCreate(BaseModel):
    github_url: str

@router.post("/", response_model=dict)
def create_repo(
    repo_in: RepoCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # Basic validation for GitHub URL
    if "github.com" not in repo_in.github_url:
        raise HTTPException(status_code=400, detail="Must be a valid github.com URL")

    # Extract repository name for the DB (e.g., from https://github.com/user/repo)
    clean_url = repo_in.github_url.rstrip("/")
    parts = clean_url.split("/")
    repo_name = f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else "unknown/repo"

    # Create Repo entry in pending state
    new_repo = Repo(
        github_url=repo_in.github_url,
        name=repo_name,
        status=RepoStatus.pending
    )
    db.add(new_repo)
    db.commit()
    db.refresh(new_repo)

    # Kick off the background task
    background_tasks.add_task(ingest_repo, repo_in.github_url, str(new_repo.id))

    return {"repo_id": str(new_repo.id), "status": "pending"}


@router.get("/{repo_id}/status")
def get_repo_status(repo_id: str, db: Session = Depends(get_db)):
    """
    Returns the current ingestion status of a repository.
    """
    import uuid
    try:
        repo_uuid = uuid.UUID(repo_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repo ID format")

    repo = db.query(Repo).filter(Repo.id == repo_uuid).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    return {
        "repo_id": str(repo.id),
        "status": repo.status.value,
        "file_count": repo.file_count,
        "name": repo.name
    }
