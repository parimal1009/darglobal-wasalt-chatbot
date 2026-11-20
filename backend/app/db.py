from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import settings

_engine: Engine | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'page',
    chunk_index INT NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    tsv tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        to_tsvector('english', coalesce(content, ''))
    ) STORED,
    UNIQUE (url, chunk_index)
);
CREATE INDEX IF NOT EXISTS documents_tsv_idx ON documents USING GIN (tsv);
"""


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = settings.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        _engine = create_engine(url, pool_pre_ping=True, pool_size=3, pool_recycle=300)
    return _engine


def init_db() -> None:
    with get_engine().begin() as conn:
        for stmt in SCHEMA.split(";"):
            if stmt.strip():
                conn.execute(text(stmt))
