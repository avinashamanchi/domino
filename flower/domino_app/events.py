"""Report what an agent is doing to the screen on its own machine (the local bridge on 127.0.0.1).

Events never go to another machine: the only thing that crosses between hospitals is a Flower message.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request


class Reporter:
    def __init__(self, bridge_url: str, who: str, run_id: int | None = None):
        self.url = (bridge_url or "").rstrip("/")
        self.who = who
        self.run_id = str(run_id) if run_id is not None else None

    def __call__(self, type_: str, **fields) -> None:
        event = {"type": type_, "who": self.who, "run_id": self.run_id, "t": round(time.time(), 3), **fields}
        line = json.dumps(event)
        print(f"DOMINO_EVENT {line}", file=sys.stderr, flush=True)
        if not self.url:
            return
        try:
            req = urllib.request.Request(self.url + "/events", data=line.encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=0.5).read()
        except Exception:  # the screen is optional; the agent never fails because of it
            pass
