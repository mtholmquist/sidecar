import json
from typing import Dict, Any

def parse_nuclei_jsonl(path: str) -> Dict[str, Any]:
    out = {"nuclei": []}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: j = json.loads(line)
                except Exception: continue
                out["nuclei"].append({
                    "severity": j.get("info",{}).get("severity","info"),
                    "id": j.get("template-id") or j.get("id","unknown"),
                    "url": j.get("matched-at") or j.get("host"),
                    "tags": (j.get("info",{}).get("tags") or "").split(","),
                })
    except Exception as e: out["error"] = str(e)
    return out
