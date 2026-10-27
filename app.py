"""Flask application for the mining analysis dashboard."""

from __future__ import annotations
import os
import secrets
import time
from collections import OrderedDict
from threading import Lock
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file
from analysis import analyze, Settings
from sources import load_source
from report import make_report

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
snapshots = OrderedDict()
lock = Lock()
report_lock = Lock()
TTL = 2 * 60 * 60


def save_snapshot(data, metadata):
    identity = secrets.token_urlsafe(24)
    with lock:
        now = time.monotonic()
        for key in list(snapshots):
            if now - snapshots[key][2] > TTL:
                del snapshots[key]
        snapshots[identity] = (data, metadata, now)
        while len(snapshots) > 20:
            snapshots.popitem(last=False)
    return identity


def get_snapshot(identity):
    if not isinstance(identity, str):
        raise ValueError("Load a data source first.")
    with lock:
        stored = snapshots.get(identity)
        if stored is None or time.monotonic() - stored[2] > TTL:
            raise ValueError(
                "The data snapshot expired. Refresh the source and try again."
            )
    return stored[0], stored[1]


def body():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return payload


@app.errorhandler(ValueError)
def invalid(exc):
    return jsonify(error=str(exc)), 400


@app.get("/api/health")
def health():
    return jsonify(status="ok")


@app.get("/api/config")
def config():
    return jsonify(sheet_url=os.environ.get("GOOGLE_SHEET_URL", ""))


@app.post("/api/load")
def load():
    args = body()
    demo = args.get("demo", False)
    if not isinstance(demo, bool):
        raise ValueError("demo must be true or false.")
    data, metadata = load_source(
        args.get("sheet_url") or os.environ.get("GOOGLE_SHEET_URL"), demo=demo
    )
    identity = save_snapshot(data, metadata)
    return jsonify(snapshot_id=identity, source=metadata)


@app.post("/api/analyze")
def calculate():
    args = body()
    data, metadata = get_snapshot(args.get("snapshot_id"))
    return jsonify(analyze(data, Settings.parse(args.get("settings")), metadata))


@app.post("/api/report")
def pdf():
    args = body()
    data, metadata = get_snapshot(args.get("snapshot_id"))
    result = analyze(data, Settings.parse(args.get("settings")), metadata)
    with report_lock:
        document = make_report(result)
    return send_file(
        document,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"mining_report_{metadata['fingerprint']}.pdf",
    )


@app.get("/")
def index():
    return send_from_directory(ROOT / "dist", "index.html")


@app.get("/<path:filename>")
def static(filename):
    return send_from_directory(ROOT / "dist", filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
