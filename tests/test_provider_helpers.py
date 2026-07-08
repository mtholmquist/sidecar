from sidecar.providers.anthropic_client import _extract_json as anthropic_extract_json
from sidecar.providers.anthropic_client import _sanitize_for_markup, _shape_plan as anthropic_shape_plan
from sidecar.providers.local_ollama import _extract_json as ollama_extract_json
from sidecar.providers.local_ollama import _normalize_base, _shape_plan as ollama_shape_plan
from sidecar.providers.openai_client import _coerce_json


def test_provider_json_extractors_accept_wrapped_json():
    wrapped = 'prefix {"next_actions": [], "notes": ["ok"], "escalation_paths": []} suffix'

    assert ollama_extract_json(wrapped)["notes"] == ["ok"]
    assert anthropic_extract_json(wrapped)["notes"] == ["ok"]


def test_shape_plan_normalizes_actions_and_markup():
    raw = {
        "actions": [{"cmd": "whoami", "reason": "[check]", "noise": "", "safety": ""}, "skip"],
        "notes": "look [here]",
        "escalation_paths": ["path"],
    }

    local = ollama_shape_plan(raw)
    anthropic = anthropic_shape_plan(raw)

    assert local["next_actions"] == [{"cmd": "whoami", "reason": "(check)", "noise": "low", "safety": "read-only"}]
    assert anthropic["next_actions"] == [{"cmd": "whoami", "reason": "[check]", "noise": "low", "safety": "read-only"}]
    assert _sanitize_for_markup("```code```\n[tag]") == "\n(tag)"


def test_openai_coerce_json_falls_back_on_unparseable_text():
    plan = _coerce_json("not json")

    assert plan["next_actions"] == []
    assert plan["escalation_paths"] == []
    assert plan["notes"][0].startswith("openai_error:could_not_parse_json")


def test_normalize_base_adds_scheme_and_strips_trailing_slash():
    assert _normalize_base("127.0.0.1:11434/") == "http://127.0.0.1:11434"
    assert _normalize_base("https://ollama.example/") == "https://ollama.example"
