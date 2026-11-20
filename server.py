import hmac
import os
import threading
import time

from flask import Flask, jsonify, request

app = Flask(__name__)
TOKEN = os.environ.get("GRADLE_TOKEN", "")   # set this on the host; use a long random string
lock = threading.Lock()
state = {}   # symbol -> command + what the EA last reported


def slot(sym):
    return state.setdefault(sym, {"version": 0, "cmd": "", "settings": {}, "seen": 0.0,
                                  "applied": 0, "ea_state": "unknown"})


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


@app.post("/command")          # called by the phone app
def command():
    d = request.get_json(silent=True) or {}
    cmd, sym = d.get("cmd"), str(d.get("symbol", "")).upper()
    if cmd not in ("start", "pause", "close") or not sym:
        return jsonify(error="bad request"), 400
    with lock:
        s = slot(sym)
        s["version"] = max(s["version"] + 1, int(time.time()))   # stays increasing across restarts
        s["cmd"] = cmd
        s["settings"] = d.get("settings", {})
        return jsonify(version=s["version"])


@app.get("/poll")              # called by the EA every few seconds
def poll():
    sym = request.args.get("symbol", "").upper()
    with lock:
        s = slot(sym)
        s["seen"] = time.time()
        s["applied"] = int(request.args.get("applied", s["applied"]))
        s["ea_state"] = request.args.get("state", s["ea_state"])
        return jsonify({"version": s["version"], "cmd": s["cmd"], **s["settings"]})


@app.get("/status")            # called by the app to see if MT5 really applied it
def status():
    sym = request.args.get("symbol", "").upper()
    with lock:
        s = slot(sym)
        return jsonify(version=s["version"], applied=s["applied"],
                       eaOnline=(time.time() - s["seen"]) < 20, state=s["ea_state"])
