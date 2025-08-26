import re
from typing import Any, Dict

# Only private IPv4 ranges are redacted; public IPs are preserved for pentesting context.
_PATTERNS = [
    (re.compile(r'(?i)\bapi[_-]?key\s*[:=]\s*["\']?([A-Za-z0-9._\-]{12,})["\']?'), 'API_KEY'),
    (re.compile(r'(?i)\bsecret[_-]?key\s*[:=]\s*["\']?([^"\']{8,})["\']?'), 'SECRET'),
    (re.compile(r'(?i)\bpassword\s*[:=]\s*["\']?([^"\']{4,})["\']?'), 'PASSWORD'),
    (re.compile(r'(?i)\bBearer\s+[A-Za-z0-9\-_\.=]+'), 'TOKEN'),
    (re.compile(r'\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b'), 'JWT'),
    (re.compile(r'\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.(?:\d{1,3}\.)\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.(?:\d{1,3}\.)\d{1,3})\b'), 'IP_PRIV'),
]

def _redact_text(s: str) -> str:
    out = s
    for pat, label in _PATTERNS:
        out = pat.sub(f'<{label}>', out)
    return out

def redact(payload: Dict[str, Any], allow_cloud: bool=False) -> Dict[str, Any]:
    """Redact sensitive strings from a nested JSON-like payload unless allow_cloud=True."""
    if allow_cloud:
        return payload
    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            return _redact_text(x)
        return x
    return walk(payload)
