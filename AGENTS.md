# AGENTS.md — how to work in this repo

## Workflow (every task)
1. **Read `memory.md` FIRST.** It's the project brain.
2. Edit only the files relevant to the task.
3. **Update `memory.md` LAST** — summarize what changed, keep it terse to minimize tokens.
4. Commit each increment with **Conventional Commits** (`feat:`, `fix:`, `chore:`, `docs:`).
5. Secrets live only in `.env` (gitignored). Never commit keys.

## UI work
Build web UI with the **frontend-design** skill — distinctive, designed output, not default
AI-slop styling. Council's verdict card (confidence dial, colour-coded juror chips, expandable
dissent panel) is the UX surface judges remember.

## Conventions
- Keep each Python file small and single-purpose (<~80 lines where practical).
- The orchestration must run **offline in mock mode** (no API key) for a deterministic demo.
- Output of `run_council.py` is a single JSON object (see `memory.md` File map / README).
- Cost stays **$0**: free OpenRouter models + optional local Ollama only. No paid models.
- Max 3 jurors in the demo.

## Run / test
- CLI:        `python run_council.py "your question"`
- Web UI:     `python server.py`  → http://localhost:8000
- Streamlit:  `streamlit run app.py`
- Smoke test: `python run_council.py "Postgres or Mongo?" | python -m json.tool`
