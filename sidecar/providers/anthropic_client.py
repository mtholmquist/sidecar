# beta
# sidecar/providers/anthropic_client.py
from __future__ import annotations

import os
import json
import re
from typing import Dict, Any, List

import requests

from ..utils.prompt import build_prompt
from ..utils.redact import redact

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")
HTTP_TIMEOUT = float(os.environ.get("AIC_ANTHROPIC_TIMEOUT", "60"))


def _extract_json(s: str) -> dict | None:
    """Grab the largest {...} block from the text and parse it."""
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
    """Normalize to {next_actions, notes, escalation_paths}."""
    plan = {"next_actions": [], "notes": [], "escalation_paths": []}
    if not isinstance(obj, dict):
        return plan

    na = obj.get("next_actions") or obj.get("actions") or []
    if isinstance(na, list):
        cleaned = []
        for a in na:
            if not isinstance(a, dict):
                continue
            cleaned.append(
                {
                    "cmd": str(a.get("cmd", "")).strip(),
                    "reason": str(a.get("reason", "")).strip(),
                    "noise": str(a.get("noise", "") or "low").strip(),
                    "safety": str(a.get("safety", "") or "read-only").strip(),
                }
            )
        plan["next_actions"] = [a for a in cleaned if a["cmd"]]

    notes = obj.get("notes")
    if isinstance(notes, list):
        plan["notes"] = [str(n) for n in notes if n]
    elif isinstance(notes, str):
        plan["notes"] = [notes]

    esc = obj.get("escalation_paths")
    if isinstance(esc, list):
        plan["escalation_paths"] = [str(x) for x in esc if x]
    elif isinstance(esc, str):
        plan["escalation_paths"] = [esc]

    return plan


def _sanitize_for_markup(s: str) -> str:
    """
    Make free-form text safe for Rich markup without changing the UI layer.
    - strip triple-backtick code fences
    - replace square brackets so they can't be parsed as markup tags
    """
    if not s:
        return ""
    s = re.sub(r"```.*?```", "", s, flags=re.S)
    s = s.replace("[", "(").replace("]", ")")
    return s


def plan_with_anthropic(model: str, payload: Dict[str, Any], allow_cloud: bool = False) -> Dict[str, Any]:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return {"next_actions": [], "notes": ["missing ANTHROPIC_API_KEY"], "escalation_paths": []}

    # Accept from arg or env; strip accidental quotes written by installers
    model = (model or os.environ.get("AIC_ANTHROPIC_MODEL", "")).strip().strip("'").strip('"')
    if not model:
        return {"next_actions": [], "notes": ["anthropic_error:empty_model"], "escalation_paths": []}

    prompt = build_prompt(redact(payload, allow_cloud=allow_cloud))
    headers = {
        "x-api-key": key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 800,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        r = requests.post(ANTHROPIC_URL, headers=headers, json=body, timeout=HTTP_TIMEOUT)
    except Exception as e:
        return {"next_actions": [], "notes": [f"anthropic_request_error:{e}"], "escalation_paths": []}

    if r.status_code >= 400:
        return {
            "next_actions": [],
            "notes": [f"anthropic_error:{r.status_code}", _sanitize_for_markup(r.text[:200])],
            "escalation_paths": [],
        }

    try:
        data = r.json()
        # content is a list of blocks; concatenate text blocks
        text = "".join(
            block.get("text", "")
            for block in (data.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
    except Exception as e:
        return {"next_actions": [], "notes": [f"anthropic_bad_json:{e}"], "escalation_paths": []}

    obj = _extract_json(text)
    if not obj:
        # Return a safe hint in notes, let the agent’s heuristics fill suggestions.
        return {
            "next_actions": [],
            "notes": ["unparsable_llm_output", _sanitize_for_markup(text)[:300]],
            "escalation_paths": [],
        }

    plan = _shape_plan(obj)
    if plan.get("notes"):
        plan["notes"] = [_sanitize_for_markup(n) for n in plan["notes"]]
    return plan
