# sidecar/sidecar/rag/query.py
from __future__ import annotations

from typing import List
from .retriever import retrieve  # type: ignore


def main(term: str) -> None:
    hits = retrieve(term, k=5)
    if not hits:
        print("No results.")
        return
    for i, h in enumerate(hits, 1):
        gist = (h["text"][:240] + "…") if len(h["text"]) > 240 else h["text"]
        print(f"[{i}] {h['title']}\n    {gist}\n    id={h['id']}\n")
