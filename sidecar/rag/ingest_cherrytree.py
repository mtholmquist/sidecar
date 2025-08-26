from bs4 import BeautifulSoup
import json, os, sys
from .db import SimpleIndex

def split_html(path: str):
    html = open(path, "r", encoding="utf-8", errors="ignore").read()
    soup = BeautifulSoup(html, "lxml")
    docs = []; sections = []; current = {"title":"Root","text":[]}
    for el in soup.body.descendants:
        if getattr(el, "name", None) in ("h1","h2"):
            if current["text"]: sections.append(current)
            current = {"title": el.get_text(strip=True), "text": []}
        elif getattr(el, "name", None) in ("p","pre","code","li"):
            current["text"].append(el.get_text(" ", strip=True))
    if current["text"]: sections.append(current)
    for sec in sections:
        title = sec["title"] or "Untitled"
        text = "\n".join(sec["text"])
        docs.append((title, text, json.dumps({"section": title})))
    return docs
def ingest_main(path: str):
    path = os.path.expanduser(path)
    if not os.path.exists(path): print(f"[!] Not found: {path}", file=sys.stderr); sys.exit(1)
    idx = SimpleIndex(os.environ.get("AIC_RAG_DB", os.path.expanduser("~/.sidecar/rag.sqlite")))
    docs = split_html(path); idx.upsert_docs(docs)
    print(f"[+] Ingested {len(docs)} sections into {idx.db_path}")
