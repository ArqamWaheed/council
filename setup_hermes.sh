#!/usr/bin/env bash
# Council — wire up Hermes Agent as the orchestrator (idempotent).
#
# This is what makes Hermes do the real work: it installs Hermes (if missing),
# hands it the OpenRouter key, registers a local Ollama provider so a hosted and
# an on-device model run through the SAME model-agnostic interface, and installs
# the learnable `council` skill. Safe to re-run.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_BIN="$(command -v hermes || echo "$HOME/.local/bin/hermes")"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Install Hermes if absent (uv-based, no sudo). Skips the interactive wizard.
if [ ! -x "$HERMES_BIN" ]; then
  echo "==> Installing Hermes Agent"
  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --skip-setup
  HERMES_BIN="$HOME/.local/bin/hermes"
fi
echo "==> Hermes: $("$HERMES_BIN" --version 2>/dev/null | head -1)"

# 2. Give Hermes the OpenRouter key from the project .env (if present).
if [ -f "$HERE/.env" ]; then
  KEY="$(grep -E '^OPENROUTER_API_KEY=' "$HERE/.env" | cut -d= -f2- || true)"
  if [ -n "${KEY:-}" ]; then
    mkdir -p "$HERMES_HOME"; touch "$HERMES_HOME/.env"
    if grep -q '^OPENROUTER_API_KEY=' "$HERMES_HOME/.env"; then
      sed -i "s|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$KEY|" "$HERMES_HOME/.env"
    else
      echo "OPENROUTER_API_KEY=$KEY" >> "$HERMES_HOME/.env"
    fi
    echo "==> Wired OpenRouter key into $HERMES_HOME/.env"
  fi
fi

# 3. Register a local Ollama provider (model-agnostic proof: hosted + local, one interface).
#    Hermes requires >=64K context, so we declare it and tell Ollama to load 64K runtime ctx.
CFG="$HERMES_HOME/config.yaml"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:0.5b}"
if [ -f "$CFG" ] && ! grep -q 'name: ollama-local' "$CFG"; then
  cat >> "$CFG" <<YAML

# Council: local on-device juror via Ollama (model-agnostic proof)
custom_providers:
  - name: ollama-local
    base_url: ${OLLAMA_BASE_URL:-http://localhost:11434/v1}
    models:
      ${OLLAMA_MODEL}:
        context_length: 65536
YAML
  # ollama_num_ctx makes Ollama actually load a 64K window so Hermes accepts it.
  grep -q 'ollama_num_ctx:' "$CFG" || sed -i '0,/^model:[[:space:]]*$/s//model:\n  ollama_num_ctx: 65536/' "$CFG"
  echo "==> Registered Hermes provider 'ollama-local' for $OLLAMA_MODEL"
fi

# 4. Install the learnable council skill into Hermes.
mkdir -p "$HERMES_HOME/skills/council"
cp "$HERE/skills/council/SKILL.md" "$HERMES_HOME/skills/council/SKILL.md"
echo "==> Installed 'council' skill into Hermes"

echo ""
echo "Hermes is now Council's orchestrator. Verify with:"
echo "  hermes skills list | grep council"
echo "  python run_council.py \"Postgres or Mongo for a new SaaS?\"   # jurors run via Hermes"
