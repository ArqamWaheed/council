"""server.py — minimal Flask endpoint serving the Council verdict UI.

Routes:
    GET  /             -> the designed single-page UI (index.html)
    POST /api/convene  -> {question} -> the council's verdict JSON
    GET  /api/history  -> recent verdicts from memory
    GET  /api/reflect  -> Hermes' proposed juror-weighting (does NOT apply it)
    POST /api/learn    -> apply an approved weighting rule
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from council import memory
from run_council import _valid_rule, learn, parse_weights, run, suggest_weight

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.post("/api/convene")
def convene_endpoint():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    # Client may carry its own learned weights (e.g. browser localStorage) so a
    # stateless deployment persists learning without a writable SKILL.md.
    extra = parse_weights(data.get("weights"))
    return jsonify(run(question, extra))


@app.get("/api/history")
def history_endpoint():
    return jsonify(memory.recall(request.args.get("q") or None))


@app.get("/api/reflect")
def reflect_endpoint():
    """Propose one weighting rule from the council's own memory — approval is the client's call."""
    suggestion = suggest_weight()
    if not suggestion:
        return jsonify({"suggestion": None,
                        "message": "Not enough signal yet — run a few more verdicts."})
    return jsonify({"suggestion": suggestion})


@app.post("/api/learn")
def learn_endpoint():
    data = request.get_json(silent=True) or {}
    rule = _valid_rule((data.get("rule") or "").strip())
    if not rule:
        return jsonify({"error": "invalid rule"}), 400
    persisted = True
    try:
        learn(rule)          # writes SKILL.md locally; may fail on a read-only deploy
    except Exception:
        persisted = False    # fine — the client keeps it in localStorage and re-sends it
    return jsonify({"applied": rule, "persisted": persisted})


if __name__ == "__main__":
    print("Council UI -> http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=False)
