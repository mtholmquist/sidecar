
<p align="center">
  <img width="512" height="512" alt="sidecar" src="https://github.com/user-attachments/assets/b060aafa-5a4d-494d-a070-dc5653e4104f" />
</p>

Decoupled AI copilot for pentesting & CTFs. Sidecar tails your shell history, parses tool outputs (any tool), grounds suggestions in your notes, and shows ranked next steps in a live TUI—without replacing your terminal.

---

## Features

* **Decoupled**: your bash/zsh stays the same; Sidecar runs alongside it.
* **Any tool support**: auto-parses files you produce (-oX, -jsonl, etc.) and can capture stdout/stderr from tools that don’t write files (via the `sc` wrapper).
* **RAG** over your methodology/notes (the repo’s `notes/methodology.html`  ingested automatically).
* **Providers**: Local (Ollama) or Cloud (OpenAI) with redaction on by default.
* **Anthropic is experimental**; not installed by default.
* **One-command launch**: sidecar up opens a 3-pane `tmux` layout (shell | agent | UI).

---

## Requirements

* Python **3.11+**
* `tmux` (for the 3-pane layout):
```bash
sudo apt-get update && sudo apt-get install -y tmux
```
* Optional (for local models): **Ollama** on `http://127.0.0.1:11434`
```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama   # optional: start on boot
curl -s http://127.0.0.1:11434/api/version && echo
```
> Ollama install is included in bootstrap if local model is selected.
* **Example models**
```bash
ollama pull llama3.2:1b
ollama pull llama3.1:8b
```

## First-time install (from GitHub)

```bash
git clone https://github.com/mtholmquist/sidecar.git
cd sidecar
chmod +x bootstrap.sh
./bootstrap.sh
```

---

## What `bootstrap.sh` does:

* Creates .venv, installs deps & the sidecar CLI (editable).
* Writes `~/.sidecar/config.yaml` (safe defaults).
* Installs shell hooks for bash/zsh (including the sc wrapper).
* Prompts for install mode:
  * Local (Ollama): asks for a model slug (e.g., `llama3.2:1b` or `llama3.1:8b`) and pulls it.
  * Cloud (OpenAI): asks for a model (default `gpt-5-nano`) and your `OPENAI_API_KEY`.
* Writes a single source of truth `~/.sidecar/.env` with your choices.
* Ingests the repo’s `notes/methodology.html` for RAG.
* Creates a `~/.local/bin/sidecar` shim so you don’t need to activate the venv.
* Prints launch command (does not auto-launch).

---

## Daily use

### Launch
```bash
sidecar up
```
This spawns the 3-pane `tmux` session:
  * **left**: your shell
  * **top-right**: the agent/log
  * **bottom (full-width)**: the UI suggestions panel

> If hooks don’t seem active, open a new terminal or run `source ~/.bashrc` or `source ~/.zshrc`.

---

## Provider & profile

The bootstrap writes defaults into `~/.sidecar/.env`. You can override at launch:

### Local (no keys, on-box)
```bash
sidecar up --provider local --profile prod-safe
```
### OpenAI (needs key & quota)
```bash
export OPENAI_API_KEY=sk-... # insert openai key
sidecar up --provider openai --profile ctf
```
### Set longer-term defaults once if you prefer:
```bash
export AIC_PROVIDER=openai     # or local
export AIC_PROFILE=ctf         # or prod-safe
sidecar up
```
### Model overrides (optional)
```bash
export AIC_LOCAL_MODEL=llama3.2:1b    # or llama3.1:8b
export AIC_OPENAI_MODEL=gpt-5-nano    # or gpt-4o-mini, etc.
```

---

### Default Tmux Pane Layout
Default tmux pane layout includes a main shell, sidecar agent logs, and sidecar UI with recommendations/notes.
<p align="center">
  <img src="https://github.com/user-attachments/assets/6173c36d-fd6d-4576-9f65-235b0eff2df5"
       alt="Sidecar tmux layout — full view"
       width="900">
</p>

<p align="center">
  
| ![Pane 1](https://github.com/user-attachments/assets/1467e051-a31f-4ac5-8869-8339c4e9ce52) | ![Pane 2](https://github.com/user-attachments/assets/c2f0cdda-736b-4407-8265-4200e9c3ed9d) | ![Pane 3](https://github.com/user-attachments/assets/15f4d7c9-02b4-4967-965c-da77322acaec) |
|:--:|:--:|:--:|
| **Pane 1 — Sidecar Terminal (shell)** | **Pane 2 — Sidecar Agent (Logs)** | **Pane 3 — Sidecar UI (Notes)** |

</p>

---

## Using the `sc` wrapper (capture stdout/stderr)

Some tools don’t write structured files—`sc` fixes that.

**What it does**: runs your command and tees output to `~/.sidecar/streams/<timestamp>-<cmd>.log` and records a pointer in `~/.sidecar/session.jsonl` so the agent can parse it.

**How to use**:
```bash
sc gobuster dir -u http://target -w /usr/share/wordlists/dirb/common.txt
sc sudo nmap -sV scanme.nmap.org
sc curl -i https://target/login
```

**When to use `sc`**: use it when a tool doesn’t write a file itself; optional otherwise.

**Where logs go**: 
```bash
ls -lt ~/.sidecar/streams | head
```
**RAG** (grounding in your notes)

Bootstrap already ingested `notes/methodology.html` from the repo.
To ingest something else (e.g., another HTML/CherryTree export):
```bash
sidecar rag ingest /path/to/your.html
# sanity check
sidecar rag query "Domain Dominance"
```

> The DB lives at `~/.sidecar/rag.sqlite` (configurable).

---

## Redaction (cloud-safety)

When using **cloud** providers (OpenAI), Sidecar **redacts** sensitive bits **by default** before sending prompts off-box (API keys, secrets, passwords, bearer tokens, JWTs, IPv4s by default).

* To **disable** (not recommended), set once before launching:
```bash
export AIC_ALLOW_CLOUD=true
sidecar up --provider openai
```
* To **tune** patterns, edit `sidecar/utils/redact.py` and restart sidecar.

> Local/Ollama never leaves your machine; redaction is skipped.

## Verifying it’s working

In the **top left** pane (your shell), run something like:
```bash
# structured outputs
nmap -p 80 -sV -oX /tmp/scan.xml scanme.nmap.org
nuclei -u https://scanme.nmap.org -jsonl -o /tmp/nuclei.jsonl

# capture stdout/stderr with sc
sc httpx -title -tech-detect -status-code -no-color -u https://scanme.nmap.org
```

You should see suggestions in the **UI** (bottom pane). For debugging:
```bash
tail -n 10 ~/.sidecar/session.jsonl
tail -n 10 ~/.sidecar/audit.jsonl
```

---

## Updating
```bash
git pull
source .venv/bin/activate
python -m pip install -e .
# or just re-run
./bootstrap.sh
```

---

## Troubleshooting
* **UI empty**: run any command; check `~/.sidecar/session.jsonl` & `~/.sidecar/audit.jsonl`.
* **No `sc` found**: `source ~/.bashrc` (or `~/.zshrc`) or open a new terminal.
* **Ollama model missing / timeouts**:
```bash
ollama list
ollama pull <model>
curl -s http://127.0.0.1:11434/api/version
```
* **Cloud 4xx / quota**: verify key, billing, and a permitted model (e.g., `gpt-4o-mini`).

## Commands reference
```bash
# launch everything
sidecar up [--provider local|openai] [--profile prod-safe|ctf]

# run components directly
sidecar agent --provider ... --profile ... [--dry-run] [--allow-cloud]
sidecar ui --audit ~/.sidecar/audit.jsonl

# RAG
sidecar rag ingest /path/to/notes.html
sidecar rag query "term"

# sc wrapper (capture stdout/stderr)
sc <any-command with args>
```

---

> **Anthropic (beta)**: not installed by `bootstrap.sh`. If you experiment, use the .beta bootstrap and corresponding provider module; models and keys must be configured manually.
