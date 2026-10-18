import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Load a .env file from the project root (or backend/) if python-dotenv is installed,
# so `uvicorn backend.main:app` works locally without exporting variables by hand.
try:
    from dotenv import load_dotenv

    _here = os.path.dirname(os.path.abspath(__file__))
    for _candidate in (
        os.path.join(_here, "..", "..", "..", ".env"),  # project root
        os.path.join(_here, "..", "..", ".env"),        # backend/
    ):
        if os.path.exists(_candidate):
            load_dotenv(_candidate, override=False)
except ImportError:  # pragma: no cover
    pass


def _normalize_db_url(url: str) -> str:
    """
    Pin the psycopg2 driver explicitly.

    SQLAlchemy 2.1+ maps a bare ``postgresql://`` URL to psycopg (v3), which is
    not installed, so the app would crash on import. Supabase/Heroku-style
    ``postgres://`` URLs are also rewritten.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


# Expects a Postgres connection string (e.g., from Supabase)
DATABASE_URL = _normalize_db_url(
    os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
