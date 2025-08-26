# sidecar/sidecar/up.py
from __future__ import annotations

import os
import shutil
import subprocess
import sys

from .utils.env import load_env


def _sh(*args, check=True, quiet=False):
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.DEVNULL if quiet else None
    return subprocess.run(list(args), check=check, stdout=stdout, stderr=stderr)

def _sh_out(*args, check=True) -> str:
    """Run tmux and return stdout (stripped)."""
    res = subprocess.run(list(args), check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return (res.stdout or "").strip()


def _read_env_file(path: str) -> dict:
    return load_env(path)


def _load_dotenv_to_tmux(env: dict):
    if not env:
        return
    for k, v in env.items():
        _sh("tmux", "setenv", "-g", k, v, check=False, quiet=True)


def up_main(provider=None, profile=None, session="sidecar", audit=None):
    # 1) Load ~/.sidecar/.env into THIS process first (source of truth)
    file_env = _read_env_file("~/.sidecar/.env")
    for k, v in file_env.items():
        os.environ.setdefault(k, v)

    # 2) Resolve provider/profile strictly from env unless CLI overrides
    provider = (provider or os.environ.get("AIC_PROVIDER") or "local").strip()
    profile = (profile or os.environ.get("AIC_PROFILE") or "prod-safe").strip()
    allow_cloud = os.environ.get("AIC_ALLOW_CLOUD", "false").lower() in ("1", "true", "yes")
    audit = audit or os.path.expanduser(os.environ.get("AIC_AUDIT_PATH", "~/.sidecar/audit.jsonl"))

    if not shutil.which("tmux"):
        print("[!] tmux is not installed. Run these in two terminals:")
        print(f"    {sys.executable} -m sidecar agent --provider {provider} --profile {profile}" + (" --allow-cloud" if allow_cloud else ""))
        print(f"    {sys.executable} -m sidecar ui --audit {audit}")
        sys.exit(1)

    # Reset session
    _sh("tmux", "kill-session", "-t", session, check=False, quiet=True)
    _sh("tmux", "start-server", check=False, quiet=True)

    # 3) Make env available to panes (tmux global env)
    _load_dotenv_to_tmux(file_env)

    # 4) tmux ergonomics
    _sh("tmux", "set-option", "-g", "mouse", "on", check=False, quiet=True)
    _sh("tmux", "set-option", "-g", "set-clipboard", "on", check=False, quiet=True)
    _sh("tmux", "set-window-option", "-g", "mode-keys", "vi", check=False, quiet=True)

    shell = os.environ.get("SHELL", "/bin/bash")
    py = sys.executable  # venv python
    ui_percent = os.environ.get("AIC_UI_PERCENT", "60")  # bottom UI height %

    # 5) Create window and capture the initial (top-left) pane id
    _sh("tmux", "new-session", "-d", "-s", session, "-n", "ops", shell)
    pentest_id = _sh_out("tmux", "display-message", "-p", "-t", f"{session}:ops.0", "#{pane_id}")

    # 6) Split vertical FROM pentest -> new pane is bottom (UI). Capture its id.
    _sh("tmux", "select-pane", "-t", pentest_id)
    _sh("tmux", "split-window", "-v", "-p", ui_percent, "-t", pentest_id, shell)
    ui_id = _sh_out("tmux", "display-message", "-p", "#{pane_id}")  # new pane is selected by default

    # 7) Split horizontal FROM pentest -> new pane is right (agent). Capture its id.
    _sh("tmux", "select-pane", "-t", pentest_id)
    _sh("tmux", "split-window", "-h", "-p", "50", "-t", pentest_id, shell)
    agent_id = _sh_out("tmux", "display-message", "-p", "#{pane_id}")  # new pane is selected

    # 8) Name panes (so the status line shows them clearly)
    _sh("tmux", "select-pane", "-t", pentest_id); _sh("tmux", "select-pane", "-T", "pentest-shell")
    _sh("tmux", "select-pane", "-t", agent_id);   _sh("tmux", "select-pane", "-T", "agent")
    _sh("tmux", "select-pane", "-t", ui_id);      _sh("tmux", "select-pane", "-T", "ui")

    # 9) Launch UI (bottom)
    _sh("tmux", "send-keys", "-t", ui_id, f"{py} -m sidecar ui --audit {audit}", "Enter")

    # 10) Launch Agent (top-right) with provider/profile
    agent_cmd = f"{py} -m sidecar agent --provider {provider} --profile {profile}"
    if allow_cloud:
        agent_cmd += " --allow-cloud"
    _sh("tmux", "send-keys", "-t", agent_id, agent_cmd, "Enter")

    # 11) Focus pentest pane and attach
    _sh("tmux", "select-pane", "-t", pentest_id)
    os.execvp("tmux", ["tmux", "attach", "-t", session])
