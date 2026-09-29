"""Domino relay: serves dist/ and a tiny message bus so the three pages can talk across Macs.

Standard library only.  Run on one Mac (e.g. the projector Mac):

    python3 relay.py            # port 8765
    python3 relay.py 9000       # another port

Every message the pages exchange passes through here; it is printed to the
terminal so you can show exactly what crossed the wire.
"""
import json
import os
import socket
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
MAX_KEEP = 500

messages = []  # list of (seq, msg)
counter = 0
cond = threading.Condition()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass  # a page reloaded or closed mid long-poll

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/bus":
            q = parse_qs(url.query)
            since = int(q.get("since", ["-1"])[0])
            wait = min(float(q.get("wait", ["20"])[0]), 25.0)
            with cond:
                if since < 0 or since > counter:
                    return self._json({"seq": counter, "messages": []})
                cond.wait_for(lambda: counter > since, timeout=wait)
                out = [m for s, m in messages if s > since]
                return self._json({"seq": counter, "messages": out})
        if url.path == "/":
            links = "".join(
                f'<li><a href="/{f}">{f}</a></li>' for f in sorted(os.listdir(ROOT)) if f.endswith(".html")
            )
            body = f"<!doctype html><meta charset=utf-8><title>Domino relay</title><ul>{links}</ul>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def do_POST(self):
        global counter
        if urlparse(self.path).path != "/bus":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n)
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)
        with cond:
            counter += 1
            messages.append((counter, msg))
            del messages[:-MAX_KEEP]
            cond.notify_all()
        if msg.get("type") != "presence":
            print(f"[wire] {len(raw):>4} B  {msg.get('from', '?'):>9} -> {msg.get('type')}: "
                  f"{json.dumps({k: v for k, v in msg.items() if k not in ('mid', 'ts')})}", flush=True)
        return self._json({"ok": True, "seq": counter})


if __name__ == "__main__":
    ip = lan_ip()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Domino relay running. Open on each Mac:")
    for f in sorted(os.listdir(ROOT)):
        if f.endswith(".html"):
            print(f"  http://{ip}:{PORT}/{f}")
    print(f"(or open the .html file directly and add ?relay={ip}:{PORT} to its address)\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
