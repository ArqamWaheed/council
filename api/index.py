"""Vercel serverless entrypoint.

Vercel's @vercel/python runtime serves the module-level WSGI callable named
`app`. We reuse the Flask app from server.py unchanged; all routes (the UI and
the /api/* endpoints) are rewritten here by vercel.json.
"""
import sys
from pathlib import Path

# server.py lives one level up; make it importable from the serverless bundle.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import app  # noqa: E402  (Flask WSGI app served by Vercel)
