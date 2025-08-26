#!/usr/bin/env bash
set -euo pipefail
echo "[+] Installing Sidecar shell hooks (bash/zsh) ..."

SIDE_STAMP_START="# >>> sidecar hooks >>>"
SIDE_STAMP_END="# <<< sidecar hooks <<<"

inject_hooks() {
  local rc="$1"
  local shelltype="$2"
  local block=""
  if [[ "$shelltype" == "bash" ]]; then
    block=$(cat <<'BASH'
# >>> sidecar hooks >>>
export AIC_LOG_PATH="${AIC_LOG_PATH:-$HOME/.sidecar/session.jsonl}"

sidecar_bash_cmdlog() {
  local EC=$?; local TS=$(date -Iseconds); local CWD="$PWD"
  TS="$TS" EC="$EC" CWD="$CWD" SC_LAST_OUT="${SC_LAST_OUT:-}" BASH_COMMAND="${BASH_COMMAND:-}" \
  python3 - <<'PY' >> "${AIC_LOG_PATH}"
import json, os
print(json.dumps({
  "ts": os.environ.get("TS",""),
  "cmd": os.environ.get("BASH_COMMAND",""),
  "exit": int(os.environ.get("EC","0")),
  "cwd": os.environ.get("CWD",""),
  "out": os.environ.get("SC_LAST_OUT","")
}))
PY
  unset SC_LAST_OUT
}
# Log after each command (idempotent)
case ":${PROMPT_COMMAND:-}:" in
  *:sidecar_bash_cmdlog:*) ;; 
  *) PROMPT_COMMAND="sidecar_bash_cmdlog${PROMPT_COMMAND:+; $PROMPT_COMMAND}";;
esac

# 'sc' wrapper: tee stdout/stderr to ~/.sidecar/streams/<ts>-<cmd>.log
sc() {
  mkdir -p "$HOME/.sidecar/streams"
  local ts=$(date +%s)
  local base
  base=$(printf "%s" "$1" | sed 's#[^A-Za-z0-9._-]#_#g')
  local out="$HOME/.sidecar/streams/${ts}-${base}.log"
  "$@" 2>&1 | tee "$out"
  export SC_LAST_OUT="$out"
}
# <<< sidecar hooks <<<
BASH
)
  else
    block=$(cat <<'ZSH'
# >>> sidecar hooks >>>
export AIC_LOG_PATH="${AIC_LOG_PATH:-$HOME/.sidecar/session.jsonl}"
preexec() { export _SC_LAST_CMD="$1"; }
precmd() {
  local ec=$?; local ts=$(date -Iseconds); local cwd="$PWD"
  TS="$ts" CMD="${_SC_LAST_CMD:-}" EC="$ec" CWD="$cwd" OUT="${_SC_LAST_OUT:-}" \
  python3 - <<'PY' >> "${AIC_LOG_PATH}"
import json, os
print(json.dumps({
  "ts": os.environ.get("TS",""),
  "cmd": os.environ.get("CMD",""),
  "exit": int(os.environ.get("EC","0")),
  "cwd": os.environ.get("CWD",""),
  "out": os.environ.get("OUT","")
}))
PY
  unset _SC_LAST_OUT
}
sc() {
  mkdir -p "$HOME/.sidecar/streams"
  local ts=$(date +%s)
  local base="${1//[^A-Za-z0-9._-]/_}"
  local out="$HOME/.sidecar/streams/${ts}-${base}.log"
  "$@" 2>&1 | tee "$out"
  export _SC_LAST_OUT="$out"
}
# <<< sidecar hooks <<<
ZSH
)
  fi

  touch "$rc"
  if ! grep -qF "$SIDE_STAMP_START" "$rc"; then
    printf "\n%s\n%s\n%s\n" "$SIDE_STAMP_START" "$block" "$SIDE_STAMP_END" >> "$rc"
    echo "[+] Appended hooks to $rc"
  else
    echo "[=] Hooks already present in $rc"
  fi
}

mkdir -p "$HOME/.sidecar/streams"
inject_hooks "$HOME/.bashrc" bash || true
inject_hooks "$HOME/.zshrc"  zsh  || true

echo "[+] Hooks installed. Open a new shell or 'source ~/.bashrc' / 'source ~/.zshrc' to activate."
