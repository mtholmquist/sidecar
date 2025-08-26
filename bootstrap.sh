#!/usr/bin/env bash
set -euo pipefail

echo "[+] sidecar bootstrap starting"
PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJ_DIR"

mkdir -p "$HOME/.sidecar" "$HOME/.sidecar/streams" "$HOME/.sidecar/notes"

# ---- Python env
if [ ! -d ".venv" ]; then
  echo "[+] creating virtualenv"
  python3 -m venv .venv --upgrade-deps
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install -e .

# ---- Choose install mode
echo ""
echo "Install mode:"
select MODE in "local (ollama)" "cloud (openai)"; do
  case $MODE in
    "local (ollama)") MODE="local"; break ;;
    "cloud (openai)") MODE="cloud"; break ;;
    *) echo "Select 1 or 2";;
  esac
done

# ---- Notes: methodology.html path (fixed, from repo)
NOTES_SRC="$PROJ_DIR/notes/methodology.html"
if [ ! -f "$NOTES_SRC" ]; then
  echo "[!] Expected notes at $NOTES_SRC but not found."
  echo "    Put your methodology.html at $PROJ_DIR/notes/methodology.html and re-run."
  exit 2
fi

# ---- .env (single source of truth)
ENV_FILE="$HOME/.sidecar/.env"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

# common defaults
grep -q '^AIC_PROFILE=' "$ENV_FILE" 2>/dev/null || echo "AIC_PROFILE=prod-safe" >> "$ENV_FILE"
grep -q '^AIC_ALLOW_CLOUD=' "$ENV_FILE" 2>/dev/null || echo "AIC_ALLOW_CLOUD=false" >> "$ENV_FILE"
grep -q '^AIC_RAG_DB=' "$ENV_FILE" 2>/dev/null || echo "AIC_RAG_DB=$HOME/.sidecar/rag.sqlite" >> "$ENV_FILE"
# fixed absolute path to methodology.html in repo
if grep -q '^AIC_NOTES_PATH=' "$ENV_FILE"; then
  sed -i "s|^AIC_NOTES_PATH=.*|AIC_NOTES_PATH=$NOTES_SRC|" "$ENV_FILE"
else
  echo "AIC_NOTES_PATH=$NOTES_SRC" >> "$ENV_FILE"
fi

if [ "$MODE" = "local" ]; then
  # Provider + model selection
  if ! command -v ollama >/dev/null 2>&1; then
    echo "[+] installing ollama"
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  echo ""
  echo "Pick an Ollama model (examples: llama3.2:1b, llama3.2:3b-instruct, llama3.1:8b)"
  read -rp "Model slug: " OMODEL
  OMODEL=${OMODEL:-llama3.2:1b}

  # persist env
  sed -i '/^AIC_PROVIDER=/d' "$ENV_FILE"; echo "AIC_PROVIDER=local" >> "$ENV_FILE"
  sed -i '/^AIC_LOCAL_MODEL=/d' "$ENV_FILE"; echo "AIC_LOCAL_MODEL='"$OMODEL"'" >> "$ENV_FILE"
  sed -i '/^OLLAMA_HOST=/d' "$ENV_FILE"; echo "OLLAMA_HOST=http://127.0.0.1:11434" >> "$ENV_FILE"
  sed -i '/^AIC_ALLOW_CLOUD=/d' "$ENV_FILE"; echo "AIC_ALLOW_CLOUD=false" >> "$ENV_FILE"

  # ensure daemon + model
  sudo systemctl enable --now ollama 2>/dev/null || true
  pgrep ollama >/dev/null || (ollama serve >/dev/null 2>&1 & sleep 1)
  echo "[+] pulling $OMODEL (if not cached)"
  ollama pull "$OMODEL" || true

else # cloud
  sed -i '/^AIC_PROVIDER=/d' "$ENV_FILE"; echo "AIC_PROVIDER=openai" >> "$ENV_FILE"
  sed -i '/^AIC_ALLOW_CLOUD=/d' "$ENV_FILE"; echo "AIC_ALLOW_CLOUD=true" >> "$ENV_FILE"

  DEFAULT_MODEL="gpt-5-nano"
  read -rp "OpenAI model (default $DEFAULT_MODEL): " OMODEL
  OMODEL=${OMODEL:-$DEFAULT_MODEL}
  sed -i '/^AIC_OPENAI_MODEL=/d' "$ENV_FILE"; echo "AIC_OPENAI_MODEL='"$OMODEL"'" >> "$ENV_FILE"

  if ! grep -q '^OPENAI_API_KEY=' "$ENV_FILE"; then
    read -rsp "Enter OPENAI_API_KEY: " OK; echo
    echo "OPENAI_API_KEY=$OK" >> "$ENV_FILE"
  fi
fi

# ---- Minimal config.yaml (logs only; models live in .env)
python - <<'PY'
import os, yaml, pathlib
cfg = {
  "logging": {
    "session_log": os.path.expanduser("~/.sidecar/session.jsonl"),
    "audit_log": os.path.expanduser("~/.sidecar/audit.jsonl")
  }
}
p = pathlib.Path(os.path.expanduser("~/.sidecar/config.yaml"))
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
print(f"[+] wrote {p}")
PY

# ---- Shell hooks
chmod +x ./install_hooks.sh
./install_hooks.sh

# ---- RAG ingest (automatic, fixed file)
# load env for this process so the subcommand sees it
set -a; . "$ENV_FILE"; set +a
python -m sidecar rag ingest "$AIC_NOTES_PATH" || {
  echo "[!] rag ingest failed"; exit 3;
}

# --- create a global shim so 'sidecar' works without activating the venv ---
SHIM="$HOME/.local/bin/sidecar"
mkdir -p "$(dirname "$SHIM")"
VENV_PY="$(command -v python)"   # this is the venv's python right now
cat > "$SHIM" <<EOF
#!/usr/bin/env bash
exec "$VENV_PY" -m sidecar "\$@"
EOF
chmod +x "$SHIM"

# Ensure ~/.local/bin is on PATH for future shells
if ! grep -Fq 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.bashrc" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi
if [ -f "$HOME/.zshrc" ] && ! grep -Fq 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.zshrc"; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
fi

echo "[+] Installed sidecar shim at $SHIM (uses this venv's python)"

echo ""
echo "[✓] Bootstrap complete."
echo "    Provider: $(grep '^AIC_PROVIDER=' "$ENV_FILE" | cut -d= -f2)"
echo "    Notes:    $(grep '^AIC_NOTES_PATH=' "$ENV_FILE" | cut -d= -f2)"
echo ""
echo "Launch when ready:"
echo "  sidecar up"
