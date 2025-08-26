# sidecar/sidecar/providers/openai_client.py
from __future__ import annotations

import json
import os
from typing import Any, Dict

from openai import OpenAI
from ..utils.redact import redact


def _want_responses_api(model: str) -> bool:
    m = (model or "").lower()
    return m.startswith("gpt-5") or m.startswith("o5")


def _system_prompt() -> str:
    return (
        "You are sidecar, an AI copilot for pentesting/CTFs. "
        "Given the terminal context (recent events, last command, parsed facts), "
        "propose actionable next steps. "
        "Respond ONLY as strict JSON matching this schema:\n"
        "{"
        "\"next_actions\":[{\"cmd\":\"\",\"reason\":\"\",\"noise\":\"low|med|high\",\"safety\":\"read-only|intrusive|exploit\"}],"
        "\"notes\":[\"...\"],"
        "\"escalation_paths\":[\"...\"]"
        "}\n"
        "Be concise and avoid repeating identical suggestions."
    )


def _user_payload(payload: Dict[str, Any]) -> str:
    slim = {
        "profile": payload.get("profile"),
        "last_cmd": payload.get("last_cmd"),
        "cwd": payload.get("cwd"),
        "exit": payload.get("exit"),
        "parsed_facts": payload.get("parsed_facts"),
        "recent_events": payload.get("recent_events", [])[-8:],
        "retrieved_snippets": payload.get("retrieved_snippets", [])[:4],
    }
    return json.dumps(slim, ensure_ascii=False)


def _coerce_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        return {"next_actions": [], "notes": [f"openai_error:could_not_parse_json: {text[:180]}"], "escalation_paths": []}


def _fallback_plan(msg: str) -> Dict[str, Any]:
    return {"next_actions": [], "notes": [msg], "escalation_paths": []}


def _call_responses(client: OpenAI, model: str, sys_prompt: str, user_blob: str) -> Dict[str, Any]:
    r = client.responses.create(
        model=model,
        input=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_blob}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    try:
        out = r.output_text
    except Exception:
        try:
            out = "".join([c.text.value for c in r.output if getattr(c, "type", "") == "output_text"])
        except Exception:
            out = ""
    return _coerce_json(out)


def _call_chat(client: OpenAI, model: str, sys_prompt: str, user_blob: str) -> Dict[str, Any]:
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_blob}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    txt = (r.choices[0].message.content or "").strip()
    return _coerce_json(txt)


def plan_with_openai(model: str, payload: Dict[str, Any], allow_cloud: bool = False) -> Dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _fallback_plan("openai_error:missing_api_key")

    # Redact unless allow_cloud given
    safe_payload = redact(payload, allow_cloud=allow_cloud)

    client = OpenAI(api_key=api_key)
    sys_prompt = _system_prompt()
    user_blob = _user_payload(safe_payload)

    models_to_try = [model]
    # Allow a comma-separated override list, otherwise use a sensible default chain
    env_fallbacks = os.environ.get("AIC_OPENAI_FALLBACKS")
    if env_fallbacks:
        models_to_try.extend([m.strip() for m in env_fallbacks.split(",") if m.strip()])
    else:
        models_to_try.extend(["gpt-4o-mini", "gpt-4o-mini-2024-07-18", "gpt-4o"])

    last_err = None
    for m in models_to_try:
        try:
            if _want_responses_api(m):
                return _call_responses(client, m, sys_prompt, user_blob)
            else:
                return _call_chat(client, m, sys_prompt, user_blob)
        except Exception as e:
            last_err = e
            # try the next model
            continue

    return _fallback_plan(f"openai_error:{last_err}; model_chain_tried={models_to_try}")
