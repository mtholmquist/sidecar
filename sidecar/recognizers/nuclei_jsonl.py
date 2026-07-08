import json
from typing import Dict, Any

def _normalize_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    if isinstance(value, str):
        return [tag.strip() for tag in value.split(",") if tag.strip()]
    return []

def parse_nuclei_jsonl(path: str) -> Dict[str, Any]:
    out = {"nuclei": []}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    j = json.loads(line)
                except Exception:
                    continue
                out["nuclei"].append({
                    "severity": j.get("info",{}).get("severity","info"),
                    "id": j.get("template-id") or j.get("id","unknown"),
                    "url": j.get("matched-at") or j.get("host"),
                    "tags": _normalize_tags(j.get("info",{}).get("tags")),
                })
    except Exception as e:
        out["error"] = str(e)
    return out
