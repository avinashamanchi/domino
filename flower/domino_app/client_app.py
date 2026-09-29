"""Hospital agent (runs on Harbor Point's Mac and on Riverbend's Mac, inside that hospital's SuperNode).

Node config (set when the SuperNode starts, never sent over the network):
    hospital='harbor'  pod_dir='/path/to/pods/harbor'  bridge_url='http://127.0.0.1:8766'
"""
import json

from flwr.app import ConfigRecord, Context, Message, RecordDict
from flwr.clientapp import ClientApp

from . import agent, wire
from .events import Reporter

app = ClientApp()


def _reporter(msg: Message, context: Context) -> Reporter:
    cfg = context.node_config
    return Reporter(str(cfg.get("bridge_url", "http://127.0.0.1:8766")), str(cfg["hospital"]), msg.metadata.run_id)


@app.query("hello")
def hello(msg: Message, context: Context) -> Message:
    report = _reporter(msg, context)
    report("hello", from_node=msg.metadata.src_node_id, message_id=msg.metadata.message_id)
    return Message(RecordDict({"hello": ConfigRecord({"hospital": str(context.node_config["hospital"])})}), reply_to=msg)


@app.query("screen")
def screen(msg: Message, context: Context) -> Message:
    report = _reporter(msg, context)
    cfg = msg.content["request"]
    request = json.loads(str(cfg["json"]))
    pace = float(cfg.get("pace", 1.0))
    report("flower.message", direction="in", message_id=msg.metadata.message_id,
           from_node=msg.metadata.src_node_id, message_type=msg.metadata.message_type)
    try:
        response = agent.handle_screen(request, str(context.node_config["pod_dir"]),
                                       str(context.node_config["hospital"]), report, pace)
    except wire.WireError as err:
        report("refused", error=str(err))
        response = {"request_id": str(request.get("request_id", "")), "candidate_token": "",
                    "candidate_found": False, "readiness": "not_applicable", "reason": "request_refused"}
    wire.check_response(response)
    reply = Message(RecordDict({"response": ConfigRecord({"json": json.dumps(response)})}), reply_to=msg)
    report("flower.message", direction="out", reply_to=msg.metadata.message_id, bytes=wire.size(response))
    return reply
