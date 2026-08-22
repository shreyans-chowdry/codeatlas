import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Text, Enum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class RepoStatus(str, enum.Enum):
    pending = "pending"
    ingesting = "ingesting"
    ready = "ready"
    failed = "failed"

class Repo(Base):
    __tablename__ = "repos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_url = Column(String, nullable=False)
    name = Column(String, nullable=False)
    status = Column(Enum(RepoStatus), default=RepoStatus.pending, nullable=False)
    file_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    files = relationship("File", back_populates="repo")
    chunks = relationship("Chunk", back_populates="repo")
    dependency_edges = relationship("DependencyEdge", back_populates="repo")
    chat_messages = relationship("ChatMessage", back_populates="repo")

class File(Base):
    __tablename__ = "files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False)
    path = Column(String, nullable=False)
    language = Column(String, nullable=True)

    repo = relationship("Repo", back_populates="files")
    chunks = relationship("Chunk", back_populates="file")

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id"), nullable=False)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False)
    symbol_name = Column(String, nullable=True)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    
    # 1024 dimensions for voyage-code-3
    embedding = Column(Vector(1024))
    
    # Generated full-text search column mapped for ORM queries (populated natively by Postgres)
    content_tsvector = Column(TSVECTOR)

    repo = relationship("Repo", back_populates="chunks")
    file = relationship("File", back_populates="chunks")

class DependencyEdge(Base):
    __tablename__ = "dependency_edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False)
    source_file_id = Column(UUID(as_uuid=True), ForeignKey("files.id"), nullable=False)
    target_file_id = Column(UUID(as_uuid=True), ForeignKey("files.id"), nullable=False)
    edge_type = Column(String, nullable=False) # e.g. "imports"

    repo = relationship("Repo", back_populates="dependency_edges")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False)
    role = Column(String, nullable=False) # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    repo = relationship("Repo", back_populates="chat_messages")
