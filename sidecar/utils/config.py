import os, yaml, pathlib

DEFAULT_CFG = {
    "profiles": {
        "prod-safe": {"noise_budget": "low", "allow_exploit": False, "prefer_machine_output": True},
        "ctf": {"noise_budget": "high", "allow_exploit": True, "prefer_machine_output": True},
    },
    "providers": {
        "local": {"type":"ollama","model": os.environ.get("AIC_LOCAL_MODEL","llama3.2:1b-instruct")},
        "openai": {"type":"openai","model": os.environ.get("AIC_OPENAI_MODEL","gpt-4o-mini"), "redact": True},
        "anthropic": {"type":"anthropic","model": os.environ.get("AIC_ANTHROPIC_MODEL","claude-3-7-sonnet-20250219"), "redact": True},
    },
    "rag": {"db": os.path.expanduser(os.environ.get("AIC_RAG_DB","~/.sidecar/rag.sqlite")), "k": 4,
            "sources":[{"name":"cherrytree", "path": os.path.expanduser(os.environ.get("AIC_NOTES_PATH","~/notes/cherrytree/index.html")),
                        "parser":"cherrytree_html","tags_from_headings": True}]},
    "logging": {"session_log": os.path.expanduser(os.environ.get("AIC_LOG_PATH","~/.sidecar/session.jsonl")),
                "audit_log": os.path.expanduser(os.environ.get("AIC_AUDIT_PATH","~/.sidecar/audit.jsonl"))}
}

def load_config():
    p = pathlib.Path(os.path.expanduser("~/.sidecar/config.yaml"))
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        def deepmerge(a,b):
            for k,v in b.items():
                if k not in a:
                    a[k]=v
                elif isinstance(v, dict):
                    a[k]=deepmerge(a.get(k,{}), v)
            return a
        return deepmerge(cfg, DEFAULT_CFG.copy())
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            yaml.safe_dump(DEFAULT_CFG, f, sort_keys=False)
        return DEFAULT_CFG
