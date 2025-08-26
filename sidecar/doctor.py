# sidecar/sidecar/doctor.py
from __future__ import annotations

import os
from .utils.env import load_env


def main():
    load_env()
    prov = os.getenv("AIC_PROVIDER", "")
    prof = os.getenv("AIC_PROFILE", "")
    allow = os.getenv("AIC_ALLOW_CLOUD", "")
    model = {
        "openai": os.getenv("AIC_OPENAI_MODEL", ""),
        "anthropic": os.getenv("AIC_ANTHROPIC_MODEL", ""),
        "local": os.getenv("AIC_LOCAL_MODEL", ""),
    }.get(prov, "")

    print(f"provider={prov}")
    print(f"profile={prof}")
    print(f"allow_cloud={allow}")
    print(f"model={model}")
    print(f"OPENAI_API_KEY set? {'yes' if os.getenv('OPENAI_API_KEY') else 'no'}")
    print(f"ANTHROPIC_API_KEY set? {'yes' if os.getenv('ANTHROPIC_API_KEY') else 'no'}")
    print(f"OLLAMA_HOST={os.getenv('OLLAMA_HOST', '')}")
