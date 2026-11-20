import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import text

from . import llm, retrieval
from .config import ROOT, settings
from .db import get_engine, init_db

app = FastAPI(title="DarGlobal & Wasalt Chatbot")

_origins = [o.strip().rstrip("/") for o in settings.cors_origins.split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT source, count(*) FROM documents GROUP BY source")).all()
    return {"status": "ok", "database": "connected", "documents": {r[0]: r[1] for r in rows}, "model": settings.llm_model, "provider": settings.llm_provider}


def _sources(ctxs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in ctxs:
        if c["url"] not in seen:
            seen.add(c["url"])
            out.append({"title": c["title"], "url": c["url"], "source": c["source"]})
    return out


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    ctxs = retrieval.search(req.message)
    messages = llm.build_messages(req.message, [m.model_dump() for m in req.history], ctxs)

    def gen():
        yield f"data: {json.dumps({'type': 'sources', 'sources': _sources(ctxs)})}\n\n"
        try:
            for tok in llm.stream_answer(messages):
                yield f"data: {json.dumps({'type': 'token', 'text': tok})}\n\n"
        except Exception as e:  # surface LLM errors to the UI
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)[:300]})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
