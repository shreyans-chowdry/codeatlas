from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import uuid

from backend.app.db.session import get_db
from backend.app.db.models import File, DependencyEdge

router = APIRouter(prefix="/repos", tags=["graph"])

@router.get("/{repo_id}/graph")
def get_dependency_graph(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Returns the internal dependency graph for a repository, shaped for frontend visualization.
    Nodes are files, edges are dependencies (e.g. imports).
    """
    files = db.query(File).filter(File.repo_id == repo_id).all()
    edges = db.query(DependencyEdge).filter(DependencyEdge.repo_id == repo_id).all()
    
    return {
        "nodes": [
            {
                "id": str(f.id),
                "path": f.path,
                "language": f.language
            } for f in files
        ],
        "edges": [
            {
                "id": str(e.id),
                "source": str(e.source_file_id),
                "target": str(e.target_file_id),
                "type": e.edge_type
            } for e in edges
        ]
    }
