import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.db.session import engine  # noqa: F401  (also loads .env)
from backend.app.routers import repos, graph, chat

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("codeatlas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables / extension / indexes on boot (idempotent). Skipped in unit tests.
    if os.getenv("SKIP_DB_INIT") != "1":
        try:
            from backend.app.db.init_db import init_db

            init_db()
        except Exception as exc:  # don't crash the server; /health will report it
            logger.error(f"Database initialisation failed: {exc}")
    yield


app = FastAPI(title="CodeAtlas AI Backend", lifespan=lifespan)

# Comma-separated list of allowed frontend origins
_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(repos.router)
app.include_router(graph.router)
app.include_router(chat.router)


@app.get("/health")
def health_check():
    """Liveness + config check so the UI can tell you exactly what's missing."""
    from sqlalchemy import text

    db_ok = True
    db_error = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc).splitlines()[0]

    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "database_error": db_error,
        "voyage_key_set": bool(os.getenv("VOYAGE_API_KEY")),
        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "github_token_set": bool(os.getenv("GITHUB_TOKEN")),
    }
