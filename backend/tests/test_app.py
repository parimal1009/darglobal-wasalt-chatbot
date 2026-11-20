import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import main, retrieval  # noqa: E402


def test_or_query_drops_stopwords():
    assert retrieval._or_query("What is the price of villas in Dubai?") == "price | villas | dubai"


def test_chat_streams_sources_and_tokens(monkeypatch):
    ctx = [{"source": "darglobal", "url": "https://x/y", "title": "T", "category": "page", "content": "c", "rank": 1.0}]
    monkeypatch.setattr(main.retrieval, "search", lambda q: ctx)
    monkeypatch.setattr(main.llm, "stream_answer", lambda m: iter(["Hel", "lo"]))
    client = TestClient(main.app)
    body = client.post("/api/chat", json={"message": "hi"}).text
    events = [json.loads(p[6:]) for p in body.split("\n\n") if p.startswith("data: ")]
    assert events[0]["type"] == "sources" and events[0]["sources"][0]["url"] == "https://x/y"
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Hello"
    assert events[-1]["type"] == "done"
