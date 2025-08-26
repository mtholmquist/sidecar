# sidecar/sidecar/utils/env.py
import os
import pathlib
from typing import Dict


def load_env(path: str = "~/.sidecar/.env") -> Dict[str, str]:
    """
    Load ~/.sidecar/.env into the current process env (without clobbering
    anything already set in the real environment). Returns the parsed dict.

    Rules:
      - Lines beginning with '#' are ignored.
      - Blank lines ignored.
      - First '=' splits KEY and VALUE; rest of the line is the value.
      - No quotes stripping (write your .env without surrounding quotes).
    """
    p = pathlib.Path(os.path.expanduser(path))
    if not p.exists():
        return {}

    env: Dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        env[k] = v
        # only set default (do not overwrite already-set real env)
        os.environ.setdefault(k, v)
    return env
