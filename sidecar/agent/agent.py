# sidecar/sidecar/agent/agent.py
from __future__ import annotations

import os
import time
import json
from typing import Dict, Any, List

from ..utils.env import load_env
from ..utils.config import load_config
from ..utils.schema import LogEvent
from ..rag.retriever import retrieve
from ..extract.generic import extract_from_file, extract_from_text, merge_facts
from ..providers.local_ollama import plan_with_ollama
from ..providers.openai_client import plan_with_openai
from ..providers.anthropic_client import plan_with_anthropic
from rich import print


def _read_new_lines(path: str, pos: int):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(pos)
        lines = f.readlines()
        pos = f.tell()
    return lines, pos


def _resolve_path(p: str, cwd: str) -> str:
    p = os.path.expanduser(p)
    if not os.path.isabs(p):
        p = os.path.normpath(os.path.join(cwd or os.getcwd(), p))
    return p


def _detect_output_paths(parts: List[str], cwd: str) -> List[str]:
    """Generic detection of output file flags and shell redirects; no tool assumptions."""
    out: List[str] = []
    i = 0
    while i < len(parts):
        t = parts[i]
        nxt = parts[i + 1] if i + 1 < len(parts) else None

        if t in ("--json", "--jsonl", "--xml", "-o", "-oX", "-oN", "-oG") and nxt:
            out.append(_resolve_path(nxt, cwd))
            i += 2
            continue

        if t.startswith("--output="):
            out.append(_resolve_path(t.split("=", 1)[1], cwd))
        elif t.startswith("-o") and len(t) > 2 and not t.startswith("-oX"):
            out.append(_resolve_path(t[2:], cwd))
        elif t == ">" and nxt:
            out.append(_resolve_path(nxt, cwd))
        i += 1

    return [p for p in out if os.path.exists(p)]


def _recent_events(session_path: str, limit: int = 20) -> List[dict]:
    try:
        with open(session_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-limit:]
        return [json.loads(l) for l in lines if l.strip().startswith("{")]
    except Exception:
        return []


def _coerce_plan(obj: Any) -> Dict[str, Any]:
    """
    Ensure the provider output conforms to the expected plan shape without
    inventing commands. If the model returns free text, surface it as a note.
    """
    plan: Dict[str, Any] = {"next_actions": [], "notes": [], "escalation_paths": []}
    if isinstance(obj, dict):
        plan["next_actions"] = list(obj.get("next_actions", [])) or []
        plan["notes"] = list(obj.get("notes", [])) or []
        plan["escalation_paths"] = list(obj.get("escalation_paths", [])) or []
        return plan
    if isinstance(obj, str) and obj.strip():
        plan["notes"] = [obj.strip()]
        return plan
    plan["notes"] = ["empty_model_response"]
    return plan


def run_agent(
    provider: str | None = None,
    profile: str | None = None,
    dry_run: bool = False,
    allow_cloud: bool = False,
    session: str | None = None,
    audit: str | None = None,
) -> None:
    """
    Agent main loop.
    - Single source of truth for provider/profile/model is ~/.sidecar/.env (loaded first).
    - config.yaml is used only for default log file locations.
    - No hardcoded tool suggestions. The model + methodology RAG drive all planning.
    - `session` / `audit` may override the log paths for tmux/up integration.
    """
    # Hydrate env from ~/.sidecar/.env (does not overwrite existing real env)
    load_env()

    # Logs (from YAML defaults, with optional CLI overrides)
    cfg = load_config()
    session_path = os.path.expanduser(session or cfg["logging"]["session_log"])
    audit_path = os.path.expanduser(audit or cfg["logging"]["audit_log"])
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    open(audit_path, "a").close()
    open(session_path, "a").close()

    # Resolve provider/profile/model strictly from env unless CLI provided overrides
    provider = (provider or os.getenv("AIC_PROVIDER") or "local").strip()
    profile = (profile or os.getenv("AIC_PROFILE") or "prod-safe").strip()

    if provider == "openai":
        model = os.getenv("AIC_OPENAI_MODEL", "gpt-5-nano").strip()
    elif provider == "anthropic":
        model = os.getenv("AIC_ANTHROPIC_MODEL", "claude-3-7-sonnet-20250219").strip()
    else:
        provider = "local"
        model = os.getenv("AIC_LOCAL_MODEL", "llama3.2:1b").strip()

    print(
        f"[bold cyan] watching {session_path} | provider={provider} "
        f"profile={profile} model={model} dry_run={dry_run}"
    )

    pos = 0
    while True:
        try:
            lines, pos = _read_new_lines(session_path, pos)
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                try:
                    evt = LogEvent.model_validate_json(line)
                except Exception:
                    continue

                # ---- GENERIC FACT EXTRACTION (no tool recognizers, no canned logic) ----
                facts: Dict[str, Any] = {}
                # learn from the command string itself
                facts = merge_facts(facts, extract_from_text(evt.cmd))

                # learn from files the command produced (flags/redirects)
                parts = evt.cmd.split()
                for pth in _detect_output_paths(parts, evt.cwd or ""):
                    facts = merge_facts(facts, extract_from_file(pth))

                # also learn from stdout/stderr captured via 'sc' wrapper
                if evt.out and os.path.exists(evt.out):
                    facts = merge_facts(facts, extract_from_file(evt.out))

                # retrieval: derive soft topics, then pull methodology chunks
                topics: List[str] = []
                ents = facts.get("entities", {})
                if ents.get("urls") or ents.get("domains"):
                    topics.append("Web")
                if ents.get("ips") or facts.get("artifacts", {}).get("ports"):
                    topics.append("Network")
                if facts.get("vulns", {}).get("cves"):
                    topics.append("Vulnerabilities")
                if facts.get("creds", {}).get("pairs") or facts.get("creds", {}).get("passwords"):
                    topics.append("Credentials")
                if not topics:
                    topics.append("General")

                retrieved = []
                for t in topics[:3]:
                    retrieved.extend(retrieve(t, k=1))

                payload = {
                    "profile": profile,
                    "recent_events": _recent_events(session_path, limit=12),
                    "last_cmd": evt.cmd,
                    "cwd": evt.cwd,
                    "exit": evt.exit,
                    "parsed_facts": facts,  # generic, tool-agnostic
                    "retrieved_snippets": [
                        {"title": r["title"], "gist": r["text"][:240], "cite_id": r["id"]}
                        for r in retrieved[:4]
                    ],
                }

                # Call the chosen provider (or dry-run)
                if dry_run:
                    plan = {"next_actions": [], "notes": ["dry-run enabled: no model call"], "escalation_paths": []}
                else:
                    try:
                        if provider == "local":
                            plan = plan_with_ollama(model=model, payload=payload)
                        elif provider == "openai":
                            plan = plan_with_openai(model=model, payload=payload, allow_cloud=allow_cloud)
                        elif provider == "anthropic":
                            plan = plan_with_anthropic(model=model, payload=payload, allow_cloud=allow_cloud)
                        else:
                            plan = {"next_actions": [], "notes": [f"unknown provider {provider}"], "escalation_paths": []}
                    except Exception as e:
                        plan = {"next_actions": [], "notes": [f"model_error:{e}"], "escalation_paths": []}

                plan = _coerce_plan(plan)

                with open(audit_path, "a", encoding="utf-8") as af:
                    af.write(
                        json.dumps(
                            {"ts": evt.ts, "cmd": evt.cmd, "cwd": evt.cwd, "exit": evt.exit, "facts": facts, "plan": plan}
                        )
                        + "\n"
                    )

                # print summary to agent log for debugging (no heuristic injection)
                if plan.get("next_actions"):
                    for i, na in enumerate(plan["next_actions"], 1):
                        print(
                            f"[green][{i}] {na.get('cmd','')}[/green] - {na.get('reason','')} "
                            f"(noise={na.get('noise','')}, safety={na.get('safety','')})"
                        )
                if plan.get("notes"):
                    print("[yellow]Notes:[/yellow]", "; ".join(plan["notes"]))

            time.sleep(0.35)
        except KeyboardInterrupt:
            print("\nbye")
            break
        except Exception as e:
            print(f"[red][!] Agent error: {e}[/red]")
            time.sleep(1.0)
