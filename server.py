import hmac
import os
import threading
import time

from flask import Flask, jsonify, request

app = Flask(__name__)
TOKEN = os.environ.get("GRADLE_TOKEN", "")
lock = threading.Lock()
state = {}


def slot(sym):
    return state.setdefault(sym, {
        "version": 0,
        "cmd": "",
        "settings": {},
        "seen": 0.0,
        "applied": 0,
        "ea_state": "unknown",
        "status_text": "Waiting for EA...",
        "balance": 0.0,
        "pnl": 0.0,
    })


@app.before_request
def guard():
    if request.endpoint == "health":
        return None
    got = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not TOKEN or not hmac.compare_digest(got, TOKEN):
        return jsonify(error="unauthorized"), 401
    return None


@app.get("/")
def health():
    return "ok"


@app.post("/command")
def command():
    d = request.get_json(silent=True) or {}
    cmd, sym = d.get("cmd"), str(d.get("symbol", "")).upper()
    if cmd not in ("start", "pause", "close") or not sym:
        return jsonify(error="bad request"), 400
    with lock:
        s = slot(sym)
        s["version"] = max(s["version"] + 1, int(time.time()))
        s["cmd"] = cmd
        s["settings"] = d.get("settings", {})
        return jsonify(version=s["version"])


@app.get("/poll")
def poll():
    sym = request.args.get("symbol", "").upper()
    with lock:
        s = slot(sym)
        s["seen"] = time.time()
        s["applied"] = int(request.args.get("applied", s["applied"]))
        s["ea_state"] = request.args.get("state", s["ea_state"])
        if "statusText" in request.args:
            s["status_text"] = request.args.get("statusText", s["status_text"])
        if "balance" in request.args:
            try:
                s["balance"] = float(request.args.get("balance", s["balance"]))
            except ValueError:
                pass
        if "pnl" in request.args:
            try:
                s["pnl"] = float(request.args.get("pnl", s["pnl"]))
            except ValueError:
                pass
        return jsonify({"version": s["version"], "cmd": s["cmd"], **s["settings"]})


@app.get("/status")
def status():
    sym = request.args.get("symbol", "").upper()
    with lock:
        s = slot(sym)
        return jsonify(
            version=s["version"],
            applied=s["applied"],
            eaOnline=(time.time() - s["seen"]) < 20,
            state=s["ea_state"],
            statusText=s["status_text"],
            balance=s["balance"],
            pnl=s["pnl"],
        )
