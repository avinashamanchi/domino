"""Domino local bridge: one per Mac, bound to 127.0.0.1 only.

  coordinator (Alder, Mac A):  serves the projector, launches `flwr run` when someone clicks
                               "Find an exchange", and relays the coordinator's events to the page.
  hospital (Harbor Point / Riverbend, Macs B and C): serves that hospital's private console and relays
                               its own agent's events to it.

Nothing here talks to another machine.  Between hospitals, the only channel is Flower.

    python3 bridge/bridge.py coordinator --port 8765
    python3 bridge/bridge.py hospital --hospital harbor --port 8766
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "dist"
RUNS = ROOT / "runs"


class Bus:
    def __init__(self, record_prefix: str):
        self.events: list[dict] = []
        self.cond = threading.Condition()
        self.prefix = record_prefix
        self.file = None

    def publish(self, event: dict) -> None:
        with self.cond:
            if event.get("type") == "run.start" or self.file is None:
                RUNS.mkdir(exist_ok=True)
                if self.file:
                    self.file.close()
                self.file = open(RUNS / f"{self.prefix}-{time.strftime('%Y%m%d-%H%M%S')}.jsonl", "a", encoding="utf-8")
            event["seq"] = len(self.events) + 1
            self.events.append(event)
            self.file.write(json.dumps(event) + "\n")
            self.file.flush()
            self.cond.notify_all()

    def since(self, seq: int, wait: float) -> list[dict]:
        with self.cond:
            self.cond.wait_for(lambda: len(self.events) > seq, timeout=wait)
            return self.events[seq:]


DECISIONS: dict[str, dict] = {}  # a person's choices on this machine, read by this machine's own agent


def make_handler(args, bus: Bus, runner):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(WEB), **k)

        def log_message(self, *_):
            pass

        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                page = "projector.html" if args.role == "coordinator" else "console.html"
                self.send_response(302)
                self.send_header("Location", f"/{page}")
                self.end_headers()
                return
            if url.path == "/config":
                return self._json({"role": args.role, "hospital": args.hospital, "live": True,
                                   "running": runner.running if runner else False, "seq": len(bus.events)})
            if url.path == "/decision":
                return self._json(DECISIONS.get(parse_qs(url.query).get("id", [""])[0], {}))
            if url.path == "/events":
                q = parse_qs(url.query)
                since = int(q.get("since", ["0"])[0])
                wait = min(float(q.get("wait", ["20"])[0]), 25)
                if since > len(bus.events):
                    since = 0
                return self._json({"events": bus.since(since, wait), "seq": len(bus.events)})
            return super().do_GET()

        def do_POST(self):
            url = urlparse(self.path)
            n = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(n) if n else b"{}"
            if url.path == "/events":  # from the Flower process on this same Mac
                try:
                    bus.publish(json.loads(body))
                except json.JSONDecodeError:
                    return self._json({"error": "bad json"}, 400)
                return self._json({"ok": True})
            if url.path == "/start" and runner:
                phase = json.loads(body or b"{}").get("phase", "search")
                return self._json(runner.start(phase))
            if url.path == "/decision":
                d = json.loads(body)
                DECISIONS[d["id"]] = {"decision": d["decision"], "hold_until": d.get("hold_until", "")}
                bus.publish({"type": "decision.clicked", "who": args.hospital, **d, "t": time.time()})
                return self._json({"ok": True})
            if url.path == "/ui" :  # UI-only events (doctor review) recorded alongside the run
                event = json.loads(body)
                event["who"] = "alder-ui"
                bus.publish(event)
                return self._json({"ok": True})
            return self._json({"error": "not found"}, 404)

    return Handler


class Runner:
    """Launches one Flower run (the coordinator ServerApp) and streams its log to the page."""

    def __init__(self, args, bus: Bus):
        self.args, self.bus, self.proc = args, bus, None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, phase: str = "search") -> dict:
        if self.running:  # the previous phase has reported phase.end; give its flwr process a moment to exit
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                return {"ok": False, "error": "a run is already in progress"}
        a = self.args
        run_config = (f"alder-pod='{Path(a.alder_pod).resolve()}' bridge-url='http://127.0.0.1:{a.port}' "
                      f"pace={a.pace} request-id='{a.request_id}' phase='{phase}' state-path='{(RUNS / 'state.json').resolve()}'")
        RUNS.mkdir(exist_ok=True)
        cmd = [a.flwr, "run", str(Path(a.flower_dir).resolve()), a.federation, "--stream", "--run-config", run_config]
        self.bus.publish({"type": "launch", "who": "bridge", "cmd": " ".join(shlex.quote(c) for c in cmd), "t": time.time()})
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                     env={**os.environ, "PYTHONUNBUFFERED": "1"})
        threading.Thread(target=self._pump, daemon=True).start()
        return {"ok": True}

    def _pump(self):
        for line in self.proc.stdout:
            line = line.rstrip()
            print(line, flush=True)
            if "DOMINO_EVENT" in line:
                continue  # already delivered over /events
            if line.strip():
                self.bus.publish({"type": "flwr.log", "who": "flwr", "line": line[-300:], "t": time.time()})
        code = self.proc.wait()
        self.bus.publish({"type": "flwr.exit", "who": "flwr", "code": code, "t": time.time()})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("role", choices=["coordinator", "hospital"])
    p.add_argument("--hospital", default="alder")
    p.add_argument("--port", type=int)
    p.add_argument("--flower-dir", default=str(ROOT / "flower"))
    p.add_argument("--federation", default="domino-local")
    p.add_argument("--flwr", default=str(ROOT / "flower" / ".venv" / "bin" / "flwr"))
    p.add_argument("--alder-pod", default=str(ROOT / "pods" / "alder"))
    p.add_argument("--request-id", default="REQ-2026-0929-A1")
    p.add_argument("--pace", type=float, default=2.0)
    args = p.parse_args()
    if args.role == "coordinator":
        args.hospital = "alder"
    args.port = args.port or (8765 if args.role == "coordinator" else 8766)

    bus = Bus(args.hospital)
    runner = Runner(args, bus) if args.role == "coordinator" else None
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args, bus, runner))
    page = "projector.html" if args.role == "coordinator" else "console.html"
    print(f"Domino {args.role} bridge ({args.hospital}) → http://127.0.0.1:{args.port}/{page}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
