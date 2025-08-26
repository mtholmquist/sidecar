import os, re
from typing import Dict, Any, List

# generic, semantic extractors (no tool names)
RE_IPV4  = re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b')
RE_IPV6  = re.compile(r'\b(?:[A-F0-9]{1,4}:){1,7}[A-F0-9]{1,4}\b', re.I)
RE_URL   = re.compile(r'https?://[^\s\'"]+', re.I)
RE_DOM   = re.compile(r'\b(?:(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})\b', re.I)
RE_EMAIL = re.compile(r'\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,63}\b', re.I)
RE_CVE   = re.compile(r'\bCVE-\d{4}-\d{4,7}\b', re.I)

RE_PORT_LINE = re.compile(r'\b(?:port|open|listening|closed|filtered)[^\n]{0,50}\b(\d{1,5})\b', re.I)
RE_SERVICE   = re.compile(r'\b(ssh|rdp|ftp|smtp|imap|pop3|http|https|smb|ldap|kerberos|dns|mysql|mssql|postgres|ntp|snmp|telnet)\b', re.I)

RE_USERPASS  = re.compile(r'\b(user(name)?|login)[\s:=]+([^\s:]+)\b.*?\b(pass(word)?)[\s:=]+([^\s]+)\b', re.I)
RE_PAIR      = re.compile(r'\b([A-Za-z0-9._\-]{1,64})[:|/]([^\s]{1,128})\b')  # loose: user:pass or user/pass
RE_FILEPATH  = re.compile(r'\b(/[^ \t\n\r\f\v]+|[A-Za-z]:\\[^ \t\n\r\f\v]+)\b')
RE_BANNER    = re.compile(r'\b(Server:|X-Powered-By:|ssh-[0-9.]+|OpenSSH[_/][0-9.]+|nginx/[0-9.]+|Apache/[0-9.]+)\b.*', re.I)
RE_ERROR     = re.compile(r'\b(denied|forbidden|unauthorized|timeout|timed out|refused|connection reset|no route|not found|exception|traceback|stack trace)\b', re.I)

def _empty() -> Dict[str, Any]:
    return {
        "entities": {"ips": [], "ipv6": [], "urls": [], "domains": [], "emails": []},
        "artifacts": {"ports": [], "services": [], "files": [], "banners": []},
        "vulns": {"cves": []},
        "creds": {"usernames": [], "passwords": [], "pairs": []},
        "errors": [],
        "indicators": []
    }

def _extend_unique(a: List, b: List):
    seen = set(a)
    for x in b:
        if x not in seen:
            a.append(x); seen.add(x)

def merge_facts(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if not base:
        base = _empty()
    if not incoming:
        return base
    # shallow/deep merge for our simple shapes
    for k in base:
        if isinstance(base[k], dict) and isinstance(incoming.get(k, None), dict):
            for sk in base[k]:
                _extend_unique(base[k][sk], incoming[k].get(sk, []))
        elif isinstance(base[k], list):
            _extend_unique(base[k], incoming.get(k, []))
    # add any new top-level keys (future-proof)
    for k, v in incoming.items():
        if k not in base:
            base[k] = v
    return base

def extract_from_text(text: str) -> Dict[str, Any]:
    out = _empty()
    if not text:
        return out

    ips = RE_IPV4.findall(text)
    ipv6 = RE_IPV6.findall(text)
    urls = RE_URL.findall(text)
    doms = [d for d in RE_DOM.findall(text) if d.lower() not in {u.split("://")[-1].split("/")[0].lower() for u in urls}]
    emails = RE_EMAIL.findall(text)
    cves = RE_CVE.findall(text)

    ports = [int(p) for p in RE_PORT_LINE.findall(text) if p.isdigit()]
    services = [s.lower() for s in RE_SERVICE.findall(text)]
    files = RE_FILEPATH.findall(text)
    banners = [m.group(0).strip() for m in RE_BANNER.finditer(text)]
    errors = [m.group(0).strip() for m in RE_ERROR.finditer(text)]

    # credentials
    for m in RE_USERPASS.finditer(text):
        out["creds"]["usernames"].append(m.group(3))
        out["creds"]["passwords"].append(m.group(6))
        out["creds"]["pairs"].append(f"{m.group(3)}:{m.group(6)}")
    # very loose pairs (filter obvious garbage)
    for u, p in RE_PAIR.findall(text):
        if len(u) <= 2 or len(p) <= 2:  # skip trivial
            continue
        out["creds"]["pairs"].append(f"{u}:{p}")

    out["entities"]["ips"] = sorted(set(ips))
    out["entities"]["ipv6"] = sorted(set(ipv6))
    out["entities"]["urls"] = sorted(set(urls))
    out["entities"]["domains"] = sorted(set(doms))
    out["entities"]["emails"] = sorted(set(emails))
    out["vulns"]["cves"] = sorted(set(cves))
    out["artifacts"]["ports"] = sorted(set(ports))
    out["artifacts"]["services"] = sorted(set(services))
    out["artifacts"]["files"] = sorted(set(files))
    _extend_unique(out["artifacts"]["banners"], banners)
    _extend_unique(out["errors"], errors)

    # high-level indicators (quick glance)
    if ips: out["indicators"].append(f"ips:{len(ips)}")
    if urls: out["indicators"].append(f"urls:{len(urls)}")
    if cves: out["indicators"].append(f"cves:{len(cves)}")
    if out["creds"]["pairs"]: out["indicators"].append(f"creds:{len(out['creds']['pairs'])}")
    if ports: out["indicators"].append(f"ports:{len(ports)}")

    return out

def extract_from_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return extract_from_text(text)
    except Exception as e:
        return {"indicators":[f"extract_error:{path}:{e}"]}
