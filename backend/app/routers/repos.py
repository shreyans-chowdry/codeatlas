import re
import uuid

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.db.models import Repo, RepoStatus, File, ChatMessage
from backend.app.ingestion.pipeline import ingest_repo

router = APIRouter(prefix="/repos", tags=["repos"])

_GITHUB_RE = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$")


class RepoCreate(BaseModel):
    github_url: str
    force: bool = False  # re-ingest even if this URL was already indexed


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repo ID format")


def _serialize(repo: Repo) -> dict:
    return {
        "repo_id": str(repo.id),
        "name": repo.name,
        "github_url": repo.github_url,
        "status": repo.status.value if hasattr(repo.status, "value") else repo.status,
        "file_count": repo.file_count,
        "error": getattr(repo, "error_message", None),
        "created_at": repo.created_at.isoformat() if repo.created_at else None,
    }


def normalize_github_url(raw: str) -> tuple[str, str]:
    """
    Accepts github.com/owner/repo, with or without scheme, trailing slash,
    `.git`, or a /tree/<branch>/... suffix. Returns (clone_url, "owner/repo").
    """
    if "github.com" not in raw:
        raise HTTPException(status_code=400, detail="Must be a valid github.com URL")
    match = _GITHUB_RE.match(raw.strip())
    if not match:
        raise HTTPException(status_code=400, detail="Must be a valid github.com URL like https://github.com/owner/repo")
    owner, name = match.group(1), match.group(2)
    return f"https://github.com/{owner}/{name}", f"{owner}/{name}"


@router.post("", response_model=dict, include_in_schema=False)
@router.post("/", response_model=dict)
def create_repo(
    repo_in: RepoCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    clone_url, repo_name = normalize_github_url(repo_in.github_url)

    # Re-use an existing index for the same repo instead of paying for embeddings again
    if not repo_in.force:
        existing = (
            db.query(Repo)
            .filter(Repo.github_url == clone_url, Repo.status.in_([RepoStatus.ready, RepoStatus.ingesting, RepoStatus.pending]))
            .order_by(Repo.created_at.desc())
            .first()
        )
        if existing is not None:
            return {"repo_id": str(existing.id), "status": existing.status.value, "reused": True}

    new_repo = Repo(github_url=clone_url, name=repo_name, status=RepoStatus.pending)
    db.add(new_repo)
    db.commit()
    db.refresh(new_repo)

    background_tasks.add_task(ingest_repo, clone_url, str(new_repo.id))

    return {"repo_id": str(new_repo.id), "status": "pending"}


@router.get("", include_in_schema=False)
@router.get("/")
def list_repos(db: Session = Depends(get_db)):
    """All indexed repositories, newest first (powers the 'recent repos' list)."""
    repos = db.query(Repo).order_by(Repo.created_at.desc()).limit(50).all()
    return [_serialize(r) for r in repos]


@router.get("/{repo_id}/status")
def get_repo_status(repo_id: str, db: Session = Depends(get_db)):
    """Returns the current ingestion status of a repository."""
    repo_uuid = _parse_uuid(repo_id)

    repo = db.query(Repo).filter(Repo.id == repo_uuid).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    return _serialize(repo)


@router.delete("/{repo_id}")
def delete_repo(repo_id: str, db: Session = Depends(get_db)):
    repo_uuid = _parse_uuid(repo_id)
    repo = db.query(Repo).filter(Repo.id == repo_uuid).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    db.delete(repo)
    db.commit()
    return {"deleted": True}


@router.get("/{repo_id}/files/{file_id}")
def get_file(repo_id: str, file_id: str, db: Session = Depends(get_db)):
    """Full source of one file (used by the file viewer and citation pills)."""
    repo_uuid, file_uuid = _parse_uuid(repo_id), _parse_uuid(file_id)
    f = db.query(File).filter(File.repo_id == repo_uuid, File.id == file_uuid).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return {"id": str(f.id), "path": f.path, "language": f.language, "content": f.content or ""}


@router.get("/{repo_id}/messages")
def get_messages(repo_id: str, db: Session = Depends(get_db)):
    """Chat history for a repository, oldest first."""
    repo_uuid = _parse_uuid(repo_id)
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.repo_id == repo_uuid)
        .order_by(ChatMessage.created_at.asc())
        .limit(200)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in msgs]


@router.delete("/{repo_id}/messages")
def clear_messages(repo_id: str, db: Session = Depends(get_db)):
    repo_uuid = _parse_uuid(repo_id)
    db.query(ChatMessage).filter(ChatMessage.repo_id == repo_uuid).delete()
    db.commit()
    return {"cleared": True}
