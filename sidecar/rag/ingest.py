# sidecar/sidecar/rag/ingest.py
from __future__ import annotations

import os
import sys
from .retriever import ingest_html, _db_path  # type: ignore


def main(path: str) -> None:
    path = os.path.expanduser(path)
    n = ingest_html(path)
    print(f"[+] Ingested {n} sections into {_db_path()}")
