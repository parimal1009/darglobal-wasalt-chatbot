# DarGlobal & Wasalt AI Chatbot

A retrieval-augmented chatbot answering questions about **Dar Global** (darglobal.co.uk) and **Wasalt** (wasalt.sa) from scraped public data.

- **Backend:** FastAPI, SQLAlchemy + psycopg, Neon Postgres (full-text search with `tsvector` + GIN index)
- **LLM:** Groq `openai/gpt-oss-120b` through the OpenAI-compatible API. Switch to an OpenRouter free model with env vars only (see `.env.example`).
- **Frontend:** React + TypeScript (Vite), streaming answers with source links
- **Deploy:** one Docker image (UI built in a Node stage, served by FastAPI) on Render free tier

**Live URL:** see the bottom of this file. The free tier sleeps after about 15 minutes idle, so the first request can take about 50 seconds.

## How it works

1. `backend/scraper/run.py` reads the sites' sitemaps, renders pages in a real browser (both sites sit behind bot protection), respects `robots.txt`, rate-limits, chunks text and upserts it into the `documents` table. It also writes `data/snapshot.json`.
2. `/api/chat` runs a Postgres full-text query for the top chunks and sends them with the question to the LLM. The system prompt restricts answers to that context.
3. The React UI streams the answer over SSE and shows source links.

## Run locally

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r backend/requirements.txt
cp .env.example .env            # fill DATABASE_URL and LLM_API_KEY
cd frontend && npm install && npm run build && cd ..
cd backend && uvicorn app.main:app --port 8000   # http://localhost:8000
```

Re-scrape (needs Edge or Chrome installed, plus `pip install playwright`): `cd backend && python -m scraper.run`.
Re-seed an empty DB from the committed snapshot: `python -m scraper.run --from-snapshot`.

## Docker

```bash
docker build -t darglobal-chatbot .
docker run -p 10000:10000 --env-file .env darglobal-chatbot
```

## Tests

`cd backend && pytest`

## Notes

- Secrets live only in `.env` / Render env vars and are git-ignored.
- Neon CLI (`neon init`) was run; `neon deploy` needs an interactive `neon login`, so the app connects with the Neon connection string via `DATABASE_URL`.
