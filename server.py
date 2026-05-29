"""server.py — minimal Flask endpoint serving the Council verdict UI.

Routes:
    GET  /             -> the designed single-page UI (index.html)
    POST /api/convene  -> {question} -> the council's verdict JSON
    GET  /api/history  -> recent verdicts from memory
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from council import memory
from run_council import run

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
    return jsonify(run(question))


@app.get("/api/history")
def history_endpoint():
    return jsonify(memory.recall(request.args.get("q") or None))


if __name__ == "__main__":
    print("Council UI -> http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=False)
