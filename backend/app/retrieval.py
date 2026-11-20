from sqlalchemy import text

from .config import settings
from .db import get_engine

SQL = text(
    """
    SELECT source, url, title, category, content,
           ts_rank(tsv, q) AS rank
    FROM documents, websearch_to_tsquery('english', :q) q
    WHERE tsv @@ q
    ORDER BY rank DESC
    LIMIT :k
    """
)

# Fallback: OR-style query so long natural questions still match something.
SQL_OR = text(
    """
    SELECT source, url, title, category, content,
           ts_rank(tsv, q) AS rank
    FROM documents, to_tsquery('english', :q) q
    WHERE tsv @@ q
    ORDER BY rank DESC
    LIMIT :k
    """
)

STOP = {"the", "a", "an", "is", "are", "of", "in", "on", "to", "and", "or", "me", "show", "what", "which", "do", "does", "you", "have", "about", "tell", "i", "can"}


def _or_query(question: str) -> str:
    words = [w for w in "".join(c if c.isalnum() else " " for c in question.lower()).split() if w not in STOP and len(w) > 1]
    return " | ".join(dict.fromkeys(words))


def search(question: str, k: int | None = None) -> list[dict]:
    k = k or settings.top_k
    with get_engine().connect() as conn:
        rows = conn.execute(SQL, {"q": question, "k": k}).mappings().all()
        if len(rows) < 2:
            oq = _or_query(question)
            if oq:
                rows = conn.execute(SQL_OR, {"q": oq, "k": k}).mappings().all()
    return [dict(r) for r in rows]
