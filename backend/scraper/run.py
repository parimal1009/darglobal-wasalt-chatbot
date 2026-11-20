"""Scrape public pages of Dar Global and Wasalt into Neon Postgres.

Usage:  python -m scraper.run [--from-snapshot]
Both sites sit behind bot protection, so pages are rendered in a real browser
(Playwright driving Microsoft Edge/Chrome). robots.txt rules are respected and
requests are rate limited. Run it locally; the deployed app only reads the DB.
"""
import gzip
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import get_engine, init_db  # noqa: E402

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "snapshot.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
DELAY = 1.5
CHUNK = 900

DG = "https://darglobal.co.uk"
WS = "https://wasalt.sa"
WS_SITEMAPS = [
    "https://cdn.wasalt.sa/sitemap/static_sitemap_en_sa.xml.gz",
    "https://cdn.wasalt.sa/sitemap/category_sitemap_en_sa.xml.gz",
    "https://cdn.wasalt.sa/sitemap/product_sitemap_en_sa.xml.gz",
]


def sitemap_urls(url: str) -> list[str]:
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
    data = r.content
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return re.findall(r"<loc>([^<]+)</loc>", data.decode("utf-8", "ignore"))


def pick_darglobal() -> list[str]:
    urls = sitemap_urls(f"{DG}/sitemap.xml")
    core, blog, press = [], [], []
    for u in urls:
        path = urlparse(u).path
        if re.match(r"^/(ar|pay-online|thank-you|success|landingpage|internship-application|bookYourUnit)", path):
            continue
        if path.startswith("/blog/"):
            blog.append(u)
        elif path.startswith("/press/"):
            press.append(u)
        else:
            core.append(u)
    return core + press[:25] + blog[:25]


def pick_wasalt() -> list[str]:
    out: list[str] = []
    for i, sm in enumerate(WS_SITEMAPS):
        try:
            urls = [u for u in sitemap_urls(sm) if "/search" not in u]
        except Exception as e:  # noqa: BLE001
            print("sitemap failed", sm, e)
            continue
        limit = [30, 30, 25][i]
        step = max(1, len(urls) // limit)
        out += urls[::step][:limit]
    return out


def clean_text(raw: str) -> str:
    lines = [ln.strip() for ln in raw.splitlines()]
    out, seen = [], set()
    for ln in lines:
        if len(ln) < 2 or ln in seen and len(ln) < 40:
            continue
        seen.add(ln)
        out.append(ln)
    return "\n".join(out)


def chunk(text_: str) -> list[str]:
    chunks, cur = [], ""
    for para in text_.split("\n"):
        if len(cur) + len(para) > CHUNK and cur:
            chunks.append(cur.strip())
            cur = ""
        cur += para + "\n"
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def category(source: str, url: str) -> str:
    p = urlparse(url).path.lower()
    for key in ("blog", "press", "projects", "partners", "faq", "about", "investor", "insights", "careers"):
        if f"/{key}" in p:
            return key
    return "page"


def scrape(urls_by_source: dict[str, list[str]]) -> list[dict]:
    from playwright.sync_api import sync_playwright

    robots = {}
    for src, base in (("darglobal", DG), ("wasalt", WS)):
        rp = RobotFileParser()
        try:
            rp.parse(httpx.get(f"{base}/robots.txt", headers={"User-Agent": UA}, timeout=30).text.splitlines())
        except Exception:  # noqa: BLE001
            rp.parse([])
        robots[src] = rp

    rows: list[dict] = []
    with sync_playwright() as p:
        browser = None
        for ch in ("msedge", "chrome", None):
            try:
                browser = p.chromium.launch(channel=ch, headless=False) if ch else p.chromium.launch()
                break
            except Exception:  # noqa: BLE001
                continue
        assert browser, "No usable browser"
        ctx = browser.new_context(locale="en-US", user_agent=UA)
        page = ctx.new_page()
        for src, urls in urls_by_source.items():
            for u in urls:
                if not robots[src].can_fetch("*", u):
                    print("robots-skip", u)
                    continue
                try:
                    if src == "wasalt":  # fresh session per page avoids Cloudflare rate flags
                        ctx.close()
                        ctx = browser.new_context(locale="en-US", user_agent=UA)
                        page = ctx.new_page()
                    page.goto(u, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3500)
                    for _ in range(6):  # wait out a Cloudflare challenge
                        if "just a moment" not in page.title().lower():
                            break
                        page.wait_for_timeout(2500)
                    if "just a moment" in page.title().lower():
                        print("blocked", u)
                        continue
                    title = page.title().strip() or u
                    for sel in ("nav", "header", "footer", "script", "style", "noscript"):
                        page.evaluate("s => document.querySelectorAll(s).forEach(e => e.remove())", sel)
                    body = clean_text(page.inner_text("body"))
                    if len(body) < 80:
                        print("thin", u)
                        continue
                    for i, c in enumerate(chunk(body)):
                        rows.append({"source": src, "url": u, "title": title, "category": category(src, u), "chunk_index": i, "content": c})
                    print(f"ok {src} {u} ({len(body)} chars)")
                except Exception as e:  # noqa: BLE001
                    print("ERR", u, str(e)[:100])
                time.sleep(DELAY if src == "darglobal" else 6)
        browser.close()
    return rows


def save(rows: list[dict]) -> None:
    init_db()
    with get_engine().begin() as conn:
        for r in rows:
            conn.execute(
                text(
                    """INSERT INTO documents (source,url,title,category,chunk_index,content)
                    VALUES (:source,:url,:title,:category,:chunk_index,:content)
                    ON CONFLICT (url, chunk_index) DO UPDATE SET
                    title=EXCLUDED.title, content=EXCLUDED.content, category=EXCLUDED.category, scraped_at=now()"""
                ),
                r,
            )
    print(f"saved {len(rows)} chunks")


if __name__ == "__main__":
    if "--from-snapshot" in sys.argv:
        save(json.loads(SNAPSHOT.read_text(encoding="utf-8")))
    else:
        only_wasalt = "--only-wasalt" in sys.argv
        targets = {"wasalt": pick_wasalt()} if only_wasalt else {"darglobal": pick_darglobal(), "wasalt": pick_wasalt()}
        rows = scrape(targets)
        SNAPSHOT.parent.mkdir(exist_ok=True)
        if only_wasalt:  # keep previously scraped darglobal rows
            old = [r for r in json.loads(SNAPSHOT.read_text(encoding="utf-8")) if r["source"] == "darglobal"]
            rows = old + rows
        SNAPSHOT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        save(rows)
