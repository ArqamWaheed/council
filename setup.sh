#!/usr/bin/env bash
# Council — one-command setup. Runs $0 in offline mock mode if you don't add an API key.
set -euo pipefail

echo "==> Creating virtualenv (.venv)"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example (offline mock mode until you add a key)"
  cp .env.example .env
fi

mkdir -p data

echo ""
echo "Council is ready."
echo "  Web UI (designed):   source .venv/bin/activate && python server.py   # http://localhost:8000"
echo "  Streamlit fallback:  source .venv/bin/activate && streamlit run app.py"
echo "  CLI:                 source .venv/bin/activate && python run_council.py \"Postgres or Mongo for a new SaaS?\""
echo ""
echo "Add your free OpenRouter key to .env to use real models. Without it, Council runs in mock mode."
