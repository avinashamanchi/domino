"""Alder's coordinator (runs on Alder's Mac, launched by the SuperLink when the projector asks for a run).

Sends the screening form to every hospital SuperNode as a real Flower message and collects the
restricted replies.  Run config: request-id, alder-pod, bridge-url, pace.
"""
import json
import time

from flwr.app import ConfigRecord, Context, Message, RecordDict
from flwr.serverapp import Grid, ServerApp

from . import coordinator, wire
from .events import Reporter

app = ServerApp()


def _wait_for_nodes(grid: Grid, want: int, timeout: float) -> list[int]:
    t0 = time.time()
    while True:
        nodes = list(grid.get_node_ids())
        if len(nodes) >= want or time.time() - t0 > timeout:
            return nodes
        time.sleep(1)


def _collect(grid: Grid, ids: list[str], timeout: float, on_reply) -> None:
    pending, t0 = set(ids), time.time()
    while pending and time.time() - t0 < timeout:
        for reply in grid.pull_messages(list(pending)):
            pending.discard(reply.metadata.reply_to_message_id)
            on_reply(reply)
        time.sleep(0.25)


@app.main()
def main(grid: Grid, context: Context) -> None:
    rc = context.run_config
    request_id, pace = str(rc["request-id"]), float(rc["pace"])
    alder_pod = str(rc["alder-pod"])
    report = Reporter(str(rc["bridge-url"]), "coordinator", context.run_id)
    wait = lambda s: time.sleep(s * pace)  # noqa: E731

    report("run.start", request_id=request_id)
    nodes = _wait_for_nodes(grid, 2, 30)
    report("nodes", node_ids=[str(n) for n in nodes])

    # Who is who: every SuperNode says which hospital it belongs to.
    hellos = [Message(RecordDict({"hello": ConfigRecord({"from": "alder"})}), dst_node_id=n, message_type="query.hello")
              for n in nodes]
    hospital_of: dict[int, str] = {}
    for reply in grid.send_and_receive(hellos, timeout=60):
        if not reply.has_error():
            hospital_of[reply.metadata.src_node_id] = str(reply.content["hello"]["hospital"])
    report("hospitals", nodes={str(n): h for n, h in hospital_of.items()})
    wait(0.8)

    # The form: built from Alder's own pod, de-identified.
    request = coordinator.build_request(alder_pod, request_id, report)
    report("form", request=request, bytes=wire.size(request))
    wait(1.5)

    targets = {n: h for n, h in hospital_of.items() if h != "alder"}
    messages = [Message(RecordDict({"request": ConfigRecord({"json": json.dumps(request), "pace": pace})}),
                        dst_node_id=n, message_type="query.screen") for n in targets]
    ids = list(grid.push_messages(messages))
    for n, mid in zip(targets, ids):
        report("ask.sent", to=targets[n], node_id=str(n), message_id=mid, bytes=wire.size(request),
               fields=sorted(request))

    replies: dict[str, dict] = {}

    def on_reply(msg: Message) -> None:
        h = hospital_of.get(msg.metadata.src_node_id, str(msg.metadata.src_node_id))
        if msg.has_error():
            report("reply.error", **{"from": h}, error=str(msg.error.reason))
            return
        response = wire.check_response(json.loads(str(msg.content["response"]["json"])))
        replies[h] = response
        report("reply.received", **{"from": h}, message_id=msg.metadata.message_id,
               reply_to=msg.metadata.reply_to_message_id, bytes=wire.size(response), response=response)

    _collect(grid, ids, 240, on_reply)
    wait(1.0)

    result = coordinator.review(replies, alder_pod)
    report("review", **result)
    report("run.end", ok=result["proposal"] is not None)
