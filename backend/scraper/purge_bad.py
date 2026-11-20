"""Remove Cloudflare/Incapsula challenge pages from DB and snapshot."""
import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import get_engine  # noqa: E402

BAD = ("performing security verification", "just a moment")
snap = Path(__file__).resolve().parents[2] / "data" / "snapshot.json"
rows = json.loads(snap.read_text(encoding="utf-8"))
good = [r for r in rows if not any(b in (r["content"] + r["title"]).lower() for b in BAD)]
snap.write_text(json.dumps(good, ensure_ascii=False, indent=1), encoding="utf-8")
with get_engine().begin() as c:
    n = c.execute(text("DELETE FROM documents WHERE content ILIKE '%performing security verification%' OR title ILIKE 'just a moment%'")).rowcount
print("snapshot", len(rows), "->", len(good), "| db deleted", n)
