"""Hospital agent (runs on each hospital's Mac, inside that hospital's SuperNode).

Node config (set when the SuperNode starts, never sent over the network):
    hospital='harbor'  pod_dir='/path/to/pods/harbor'  bridge_url='http://127.0.0.1:8766'
"""
import json
import time
import urllib.request

from flwr.app import ConfigRecord, Context, Message, RecordDict
from flwr.clientapp import ClientApp

from . import agent, agent2, wire
from .events import Reporter

app = ClientApp()


def _ctx(msg: Message, context: Context):
    cfg = context.node_config
    hospital = str(cfg["hospital"])
    bridge = str(cfg.get("bridge_url", "http://127.0.0.1:8766"))
    return hospital, str(cfg["pod_dir"]), bridge, Reporter(bridge, hospital, msg.metadata.run_id)


def _decider(bridge: str, report, msg_id: str):
    """Ask this hospital's person. Routine answers go out after a short countdown; a hold waits for the person."""
    def decide(kind, pair, advice, **extra):
        did = f"{msg_id[:10]}-{kind}-{pair}"
        needs_person = advice["decision"] in ("hold", "decline")
        timeout = 150 if needs_person and kind == "approve" else 7
        report("decision.request", id=did, kind=kind, pair=pair, advice=advice, timeout=timeout, **extra)
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                r = json.loads(urllib.request.urlopen(f"{bridge}/decision?id={did}", timeout=1).read())
            except Exception:
                r = {}
            if r.get("decision"):
                report("decision.made", id=did, by="person", **r)
                return r
            time.sleep(0.4)
        r = {"decision": advice["decision"], "hold_until": advice.get("hold_until", "")}
        report("decision.made", id=did, by="countdown", **r)
        return r
    return decide


def _reply(msg: Message, kind: str, payload: dict, report) -> Message:
    wire.check_reply(kind, payload)
    report("flower.message", direction="out", kind=kind, reply_to=msg.metadata.message_id, bytes=wire.size(payload), response=payload)
    return Message(RecordDict({"reply": ConfigRecord({"json": json.dumps(payload)})}), reply_to=msg)


def _handle(kind, fn):
    def handler(msg: Message, context: Context) -> Message:
        hospital, pod_dir, bridge, report = _ctx(msg, context)
        req = json.loads(str(msg.content["ask"]["json"]))
        pace = float(msg.content["ask"].get("pace", 1.0))
        wire.check_ask(kind, req)
        report("flower.message", direction="in", kind=kind, message_id=msg.metadata.message_id,
               from_node=str(msg.metadata.src_node_id), bytes=wire.size(req), request=req)
        payload = fn(req, pod_dir, hospital, report, pace, _decider(bridge, report, msg.metadata.message_id))
        return _reply(msg, kind, payload, report)
    return handler


@app.query("hello")
def hello(msg: Message, context: Context) -> Message:
    hospital, _, _, report = _ctx(msg, context)
    report("hello", from_node=str(msg.metadata.src_node_id))
    return Message(RecordDict({"hello": ConfigRecord({"hospital": hospital})}), reply_to=msg)


app.query("profiles")(_handle("profiles", lambda q, d, h, r, p, _: agent2.profiles(q, d, h, r, p)))
app.query("compat")(_handle("compat", lambda q, d, h, r, p, _: agent2.compat(q, d, h, r, p)))
app.query("approve")(_handle("approve", lambda q, d, h, r, p, dec: agent2.approve(q, d, h, r, dec, p)))
app.query("hold")(_handle("hold", lambda q, d, h, r, p, dec: agent2.hold(q, d, h, r, dec, p)))


@app.query("screen")  # the earlier single-form flow, kept for its tests
def screen(msg: Message, context: Context) -> Message:
    hospital, pod_dir, _, report = _ctx(msg, context)
    cfg = msg.content["request"]
    response = agent.handle_screen(json.loads(str(cfg["json"])), pod_dir, hospital, report, float(cfg.get("pace", 1.0)))
    return Message(RecordDict({"response": ConfigRecord({"json": json.dumps(response)})}), reply_to=msg)
