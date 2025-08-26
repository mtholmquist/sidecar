# sidecar/sidecar/rag/retriever.py
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

from bs4 import BeautifulSoup


def _db_path() -> str:
    return os.path.expanduser(os.environ.get("AIC_RAG_DB", "~/.sidecar/rag.sqlite"))


def _conn() -> sqlite3.Connection:
    p = _db_path()
    Path(os.path.dirname(p)).mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


def _init_db(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks(
          id    TEXT PRIMARY KEY,
          title TEXT,
          text  TEXT,
          tags  TEXT
        );
        """
    )
    # FTS table (no UPSERT support)
    con.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
        USING fts5(text, title, tags);
        """
    )


def _upsert_chunk(con: sqlite3.Connection, cid: str, title: str, text: str, tags_csv: str) -> None:
    """
    1) Upsert into the base table (supported).
    2) Mirror into the FTS table using INSERT OR REPLACE (supported by FTS5).
    """
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO chunks(id,title,text,tags)
        VALUES(?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          title=excluded.title,
          text =excluded.text,
          tags =excluded.tags;
        """,
        (cid, title, text, tags_csv),
    )
    # Get the current rowid and refresh the FTS entry.
    rowid = cur.execute("SELECT rowid FROM chunks WHERE id=?", (cid,)).fetchone()[0]
    cur.execute(
        "INSERT OR REPLACE INTO chunks_fts(rowid, text, title, tags) VALUES (?, ?, ?, ?);",
        (rowid, text, title, tags_csv),
    )


def _norm(s: str) -> str:
    return " ".join((s or "").split())


def _chunk_html(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Very simple chunker:
    - Start a new chunk at each H1/H2.
    - Accumulate paragraph text until the next heading.
    - Keep the heading as title; use heading text as a tag.
    """
    chunks: List[Dict[str, str]] = []
    cur_title: str | None = None
    cur_buf: List[str] = []
    cur_tag: str = ""

    for el in soup.find_all(["h1", "h2", "p", "li", "pre", "code"]):
        name = el.name.lower()
        if name in ("h1", "h2"):
            # flush previous
            if cur_title and cur_buf:
                chunks.append(
                    {
                        "title": _norm(cur_title),
                        "text": _norm("\n".join(cur_buf)),
                        "tags": cur_tag,
                    }
                )
            cur_title = el.get_text(" ", strip=True)
            cur_tag = cur_title
            cur_buf = []
        else:
            txt = el.get_text(" ", strip=True)
            if txt:
                cur_buf.append(txt)

    if cur_title and cur_buf:
        chunks.append({"title": _norm(cur_title), "text": _norm("\n".join(cur_buf)), "tags": cur_tag})

    # fallback if no headings
    if not chunks:
        whole = _norm(soup.get_text(" ", strip=True))
        if whole:
            chunks.append({"title": "Notes", "text": whole[:6000], "tags": "General"})
    return chunks


def ingest_html(path: str) -> int:
    """
    Parse an HTML export (e.g., your methodology.html), chunk it, and index into SQLite + FTS.
    Idempotent: uses stable ids based on (path, index, title).
    """
    path = os.path.expanduser(path)
    with open(path, "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    chunks = _chunk_html(soup)

    con = _conn()
    _init_db(con)

    n = 0
    for i, ch in enumerate(chunks):
        title = ch["title"]
        text = ch["text"]
        tags_csv = ",".join(t.strip() for t in (ch.get("tags") or "General").split(",") if t.strip()) or "General"
        cid = hashlib.sha1(f"{path}:{i}:{title}".encode("utf-8")).hexdigest()
        _upsert_chunk(con, cid, title, text, tags_csv)
        n += 1

    con.commit()
    con.close()
    return n


def retrieve(topic: str, k: int = 4) -> List[Dict[str, Any]]:
    """
    Simple FTS-backed retrieval: MATCH on the topic and return text + metadata.
    """
    con = _conn()
    _init_db(con)
    cur = con.cursor()
    rows = cur.execute(
        """
        SELECT c.id, c.title, c.tags, c.text
        FROM chunks_fts f
        JOIN chunks c ON c.rowid = f.rowid
        WHERE chunks_fts MATCH ?
        LIMIT ?;
        """,
        (topic, int(k)),
    ).fetchall()
    con.close()

    return [{"id": r["id"], "title": r["title"], "tags": r["tags"], "text": r["text"]} for r in rows]
