import re
from typing import Dict, Any
def parse_httpx_lines(path: str) -> Dict[str, Any]:
    out = {"web_tech": []}
    tech_re = re.compile(r'\[(\d{3})\]\s+([^\s]+).*?\[(.*?)\]')
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = tech_re.search(line)
                if not m: continue
                status, url, meta = m.groups()
                out["web_tech"].append({"host": url, "tech": meta, "evidence": status})
    except Exception as e: out["error"] = str(e)
    return out
