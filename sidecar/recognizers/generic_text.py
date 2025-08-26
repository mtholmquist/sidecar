import re
from typing import Dict, Any
IP_RE = re.compile(r'(?:\b\d{1,3}\.){3}\d{1,3}\b')
URL_RE = re.compile(r'\bhttps?://[\w\.-]+(?:/[\w\./%\-?=&]*)?')
CVE_RE = re.compile(r'\bCVE-\d{4}-\d{4,7}\b', re.IGNORECASE)
HASH_RE = re.compile(r'\b[a-f0-9]{32,64}\b', re.IGNORECASE)
def parse_generic(path: str) -> Dict[str, Any]:
    out = {"indicators": []}
    try:
        txt = open(path, "r", encoding="utf-8", errors="ignore").read()
        for ip in set(IP_RE.findall(txt)): out["indicators"].append({"type":"ip", "value": ip})
        for url in set(URL_RE.findall(txt)): out["indicators"].append({"type":"url", "value": url})
        for cve in set(CVE_RE.findall(txt)): out["indicators"].append({"type":"cve", "value": cve.upper()})
        for h in set(HASH_RE.findall(txt)): out["indicators"].append({"type":"hash", "value": h})
    except Exception as e: out["error"] = str(e)
    return out
