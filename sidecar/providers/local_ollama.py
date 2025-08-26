# sidecar/providers/local_ollama.py
from __future__ import annotations

import os
import json
import time
import subprocess
from typing import Dict, Any, List, Optional

import requests


# ---- Endpoint & timeouts ----------------------------------------------------

def _normalize_base(u: Optional[str]) -> str:
    u = (u or "").strip()
    if not u:
        return "http://127.0.0.1:11434"
    if not (u.startswith("http://") or u.startswith("https://")):
        u = "http://" + u
    return u.rstrip("/")

# Prefer OLLAMA_URL if set; fall back to OLLAMA_HOST for compatibility
OLLAMA_URL = _normalize_base(
    os.environ.get("OLLAMA_URL") or os.environ.get("OLLAMA_HOST")
)

# Local models can be slow; make this generous (override with AIC_OLLAMA_TIMEOUT)
HTTP_TIMEOUT = float(os.environ.get("AIC_OLLAMA_TIMEOUT", "120.0"))


# ---- Small helpers ----------------------------------------------------------

def _clean_tag(tag: Optional[str]) -> str:
    """Strip whitespace and any accidental shell quotes from a model tag."""
    if not tag:
        return ""
    return tag.strip().strip('"').strip("'")


def _sanitize(s: Any) -> str:
    """Avoid Rich/Textual markup collisions and keep lines tidy."""
    s = str(s)
    return s.replace("[", "(").replace("]", ")").strip()


def _http_get(path: str) -> requests.Response:
    return requests.get(f"{OLLAMA_URL}{path}", timeout=HTTP_TIMEOUT)


def _http_post(path: str, data: dict) -> requests.Response:
    return requests.post(f"{OLLAMA_URL}{path}", json=data, timeout=HTTP_TIMEOUT)


def _try_start_server() -> bool:
    """Best-effort start of `ollama serve` in background, then quick recheck."""
    try:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    # Give it a moment to bind the port
    for _ in range(10):
        try:
            r = _http_get("/api/version")
            if r.ok:
                return True
        except Exception:
            time.sleep(0.3)
    return False


def _ensure_server() -> Optional[str]:
    """Return None if server reachable, else an error string (after trying to start)."""
    try:
        r = _http_get("/api/version")
        if r.ok:
            return None
        # Not-ok HTTP—no point trying to serve, but report.
        return f"ollama_error:http_{r.status_code}"
    except Exception:
        # Try to boot it once
        if _try_start_server():
            return None
        return "ollama_error:server_unreachable"


def _installed_models() -> List[str]:
    try:
        r = _http_get("/api/tags")
        if not r.ok:
            return []
        data = r.json()
        # schema: {"models":[{"name":"llama3.2:1b", ...}, ...]}
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def _pull_model(tag: str) -> Optional[str]:
    """
    Pull a model via the 'ollama' CLI (more reliable for progress/errors).
    Returns None on success, or an error string on failure.
    """
    if not tag:
        return "ollama_pull_failed:empty_tag"

    try:
        # No quotes around tag in argv – quoting breaks the name (causes 400).
        cp = subprocess.run(
            ["ollama", "pull", tag],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if cp.returncode == 0:
            return None
        return f"ollama_pull_failed:exit_{cp.returncode}"
    except FileNotFoundError:
        return "ollama_pull_failed:binary_not_found"
    except subprocess.CalledProcessError as e:
        return f"ollama_pull_failed:{(e.stdout or '').strip() or e}"


def _extract_json(s: str) -> Optional[dict]:
    """
    Try to extract a JSON object from an LLM response (which may include prose).
    We take the largest {...} block and parse it.
    """
    if not s:
        return None
    first = s.find("{")
    last = s.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    try:
        return json.loads(s[first : last + 1])
    except Exception:
        return None


def _shape_plan(obj: dict) -> dict:
    """
    Normalize a model's JSON into Sidecar's plan shape.
    Expected keys:
      - next_actions: List[{cmd, reason, noise, safety}]
      - notes: List[str]
      - escalation_paths: List[str]
    """
    plan = {
        "next_actions": [],
        "notes": [],
        "escalation_paths": [],
    }

    if isinstance(obj, dict):
        na = obj.get("next_actions") or obj.get("actions") or []
        if isinstance(na, list):
            cleaned = []
            for a in na:
                if not isinstance(a, dict):
                    continue
                cleaned.append(
                    {
                        "cmd": _sanitize(a.get("cmd", "")),
                        "reason": _sanitize(a.get("reason", "")),
                        "noise": _sanitize(a.get("noise", "") or "low").lower(),
                        "safety": _sanitize(a.get("safety", "") or "read-only").lower(),
                    }
                )
            plan["next_actions"] = [a for a in cleaned if a["cmd"]]

        notes = obj.get("notes") or []
        if isinstance(notes, list):
            plan["notes"] = [_sanitize(n) for n in notes if n]
        elif isinstance(notes, str):
            plan["notes"] = [_sanitize(notes)]

        esc = obj.get("escalation_paths") or []
        if isinstance(esc, list):
            plan["escalation_paths"] = [_sanitize(x) for x in esc if x]
        elif isinstance(esc, str):
            plan["escalation_paths"] = [_sanitize(esc)]

    return plan


def _build_prompt(payload: Dict[str, Any]) -> str:
    """
    Build a compact instruction prompt for small local models.
    The model must output ONLY a JSON object with keys:
      next_actions, notes, escalation_paths.
    """
    last_cmd = payload.get("last_cmd") or ""
    cwd = payload.get("cwd") or ""
    exit_code = payload.get("exit")
    facts = payload.get("parsed_facts") or {}
    snippets = payload.get("retrieved_snippets") or []
    recent = payload.get("recent_events") or []

    # keep it short – local models have tight context windows
    snippet_lines = []
    for s in snippets[:4]:
        title = s.get("title", "")[:80]
        gist = s.get("gist", "")[:220].replace("\n", " ")
        snippet_lines.append(f"- {title}: {gist}")

    recent_lines = []
    for e in recent[-6:]:
        try:
            cmd = e.get("cmd", "")[:140]
            rc = e.get("exit", "")
            recent_lines.append(f"- rc={rc} :: {cmd}")
        except Exception:
            continue

    instruction = f"""
You are a penetration testing copilot. Based ONLY on the context below,
propose the next shell commands to run. Be concise and pragmatic.

Output STRICT JSON with the following shape and NOTHING else:

{{
  "next_actions": [{{"cmd": "...", "reason": "...", "noise": "low|med|high", "safety": "read-only|intrusive|exploit"}}],
  "notes": ["..."],
  "escalation_paths": ["..."]
}}

Guidelines:
- Prefer low-noise, read-only enumeration first.
- Use context from previous commands, artifacts, and retrieved notes.
- Do not invent targets or credentials; rely on provided facts.
- If no stdout/stderr was captured, suggest re-running via the capture wrapper.
- Keep 'cmd' runnable as-is in a typical Kali shell.

Context:
- cwd: {cwd}
- last_cmd: {last_cmd}
- last_exit: {exit_code}

Facts (parsed):
{json.dumps(facts)[:1600]}

Recent:
{os.linesep.join(recent_lines)}

Methodology notes:
{os.linesep.join(snippet_lines)}
"""
    return instruction.strip()


def _generate_once(model: str, prompt: str) -> requests.Response:
    """Single /api/generate call with stream disabled."""
    return _http_post(
        "/api/generate",
        {
            "model": model,           # IMPORTANT: unquoted clean tag
            "prompt": prompt,
            "stream": False,
            # optional generation knobs:
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
                "num_ctx": 4096,
            },
        },
    )


def plan_with_ollama(model: str, payload: Dict[str, Any], allow_cloud: bool = False) -> Dict[str, Any]:
    """
    Generate a Sidecar plan using a local Ollama model.
    Returns a dict with keys: next_actions, notes, escalation_paths.
    """
    notes: List[str] = []

    # 1) Server reachable (try to start if down)
    server_err = _ensure_server()
    if server_err:
        return {"next_actions": [], "notes": [_sanitize(server_err)], "escalation_paths": []}

    # 2) Resolve and sanitize model tag
    model = _clean_tag(model or os.environ.get("AIC_LOCAL_MODEL", "llama3.2:1b"))
    if not model:
        return {"next_actions": [], "notes": ["ollama_error:empty_model_tag"], "escalation_paths": []}

    # 3) Ensure model is present; pull if missing
    installed = _installed_models()
    if model not in installed:
        notes.append(f"ollama_model_missing:'{model}'")
        pull_err = _pull_model(model)
        if pull_err:
            notes.append(pull_err)
            return {"next_actions": [], "notes": notes, "escalation_paths": []}

    # 4) Build prompt and call /api/generate (with one intelligent retry)
    prompt = _build_prompt(payload)

    try:
        r = _generate_once(model, prompt)
    except Exception as e:
        notes.append(f"ollama_request_error:{e}")
        return {"next_actions": [], "notes": notes, "escalation_paths": []}

    if not r.ok:
        # Common issues: 400 invalid model name, 500 OOM, etc.
        err_text = ""
        try:
            err_json = r.json()
            err_text = json.dumps(err_json)
        except Exception:
            err_text = r.text

        # If we got a 400 invalid model name (can happen despite tags),
        # try a pull once and retry.
        if r.status_code == 400 and "invalid model name" in (err_text or "").lower():
            pull_err = _pull_model(model)
            if pull_err:
                notes.append(pull_err)
                return {"next_actions": [], "notes": notes, "escalation_paths": []}
            try:
                r = _generate_once(model, prompt)
            except Exception as e:
                notes.append(f"ollama_request_error:{e}")
                return {"next_actions": [], "notes": notes, "escalation_paths": []}
            if not r.ok:
                try:
                    err_json = r.json()
                    err_text = json.dumps(err_json)
                except Exception:
                    err_text = r.text
                notes.append(f"ollama_http_error:{r.status_code}")
                notes.append(_sanitize(err_text))
                return {"next_actions": [], "notes": notes, "escalation_paths": []}
        else:
            notes.append(f"ollama_http_error:{r.status_code}")
            notes.append(_sanitize(err_text))
            return {"next_actions": [], "notes": notes, "escalation_paths": []}

    # Parse response
    try:
        data = r.json()
        raw = data.get("response", "") or ""
    except Exception as e:
        notes.append(f"ollama_bad_json:{e}")
        return {"next_actions": [], "notes": notes, "escalation_paths": []}

    obj = _extract_json(raw)
    if not obj:
        # Some tiny models drift—fallback: provide a hint and let agent heuristics kick in.
        notes.append("parse_error:response_not_json")
        notes.append(_sanitize(raw[:240]))
        return {"next_actions": [], "notes": notes, "escalation_paths": []}

    plan = _shape_plan(obj)
    if notes:
        plan["notes"] = (plan.get("notes") or []) + notes
    return plan
