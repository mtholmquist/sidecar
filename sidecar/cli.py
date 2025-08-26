# sidecar/sidecar/cli.py
from __future__ import annotations

import argparse
import sys
from .agent.agent import run_agent


def _run_ui(path: str) -> None:
    """
    Import the UI runner from sidecar.ui.ui (preferred) or sidecar.ui.tui (legacy),
    and call it with the audit path as a *positional* argument so we don't care
    what the parameter is named inside the module.
    """
    run = None
    try:
        from .ui.ui import run_ui as run
    except Exception:
        try:
            from .ui.tui import run_ui as run
        except Exception as e:
            print(f"[!] ui not available: {e}", file=sys.stderr)
            sys.exit(1)
    run(path)  # positional call avoids keyword-mismatch across versions


def _rag_ingest(path: str) -> None:
    from .rag.retriever import ingest_html
    n = ingest_html(path)
    print(f"[+] Ingested {n} sections into your RAG DB")


def main() -> int:
    p = argparse.ArgumentParser(prog="sidecar")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("agent", help="run background planning agent")
    a.add_argument("--provider", default="local", choices=["local", "openai", "anthropic"])
    a.add_argument("--profile", default="prod-safe", choices=["prod-safe", "ctf"])
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--allow-cloud", action="store_true", help="permit sending non-redacted detail to cloud")

    u = sub.add_parser("ui", help="TUI to view suggestions")
    u.add_argument("--audit", required=True, help="path to audit.jsonl")

    r = sub.add_parser("rag", help="RAG utilities")
    rsub = r.add_subparsers(dest="ragcmd", required=True)
    ri = rsub.add_parser("ingest", help="ingest HTML knowledge base")
    ri.add_argument("path")

    up = sub.add_parser("up", help="launch tmux layout with agent (background) + UI + shell")

    args = p.parse_args()

    if args.cmd == "agent":
        run_agent(provider=args.provider, profile=args.profile, dry_run=args.dry_run, allow_cloud=args.allow_cloud)
        return 0
    if args.cmd == "ui":
        _run_ui(args.audit)
        return 0
    if args.cmd == "rag" and args.ragcmd == "ingest":
        _rag_ingest(args.path)
        return 0
    if args.cmd == "up":
        from .up import up_main
        up_main()
        return 0

    return 1
