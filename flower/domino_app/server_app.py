"""Coordinator (runs on Alder's Mac, launched by the SuperLink when the projector starts a phase).

Phases (run config `phase`):
  search   - collect donor profiles, ask every hospital which donors fit its own patients, find the best loop
  approve  - each hospital in the plan approves (a person decides); a hold request goes to the others;
             no consensus -> re-plan without the held pair
  chain    - a stranger's kidney starts a chain through the remaining pairs
Every exchange between machines is a Flower message. State between phases lives in a local file on Alder's Mac.
"""
import json
import time
from pathlib import Path

from flwr.app import ConfigRecord, Context, Message, RecordDict
from flwr.serverapp import Grid, ServerApp

from . import matching, wire
from .events import Reporter

app = ServerApp()
SURGERY_DATE = "2026-10-02"


def _wait_nodes(grid: Grid, want: int, timeout: float) -> list[int]:
    t0 = time.time()
    while True:
        nodes = list(grid.get_node_ids())
        if len(nodes) >= want or time.time() - t0 > timeout:
            return nodes
        time.sleep(1)


class Coord:
    def __init__(self, grid: Grid, report, pace: float):
        self.grid, self.report, self.pace = grid, report, pace
        self.node_of: dict[str, int] = {}

    def hello(self):
        nodes = _wait_nodes(self.grid, 3, 45)
        msgs = [Message(RecordDict({"hello": ConfigRecord({"from": "alder"})}), dst_node_id=n, message_type="query.hello") for n in nodes]
        for r in self.grid.send_and_receive(msgs, timeout=60):
            if not r.has_error():
                self.node_of[str(r.content["hello"]["hospital"])] = r.metadata.src_node_id
        self.report("hospitals", nodes={str(n): h for h, n in self.node_of.items()})

    def ask(self, kind: str, per_hospital: dict[str, dict], timeout: float = 120) -> dict[str, dict]:
        """Send one Flower message per hospital; collect the replies as they arrive."""
        targets = {h: self.node_of[h] for h in per_hospital if h in self.node_of}
        msgs = []
        for h, n in targets.items():
            wire.check_ask(kind, per_hospital[h])
            msgs.append(Message(RecordDict({"ask": ConfigRecord({"json": json.dumps(per_hospital[h]), "pace": self.pace})}),
                                dst_node_id=n, message_type=f"query.{kind}"))
        ids = list(self.grid.push_messages(msgs))
        hosp_of_id = {}
        for (h, _), mid, m in zip(targets.items(), ids, msgs):
            hosp_of_id[mid] = h
            self.report("ask.sent", to=h, kind=kind, message_id=mid, bytes=wire.size(per_hospital[h]), fields=sorted(per_hospital[h]))
        replies, pending, t0 = {}, set(ids), time.time()
        while pending and time.time() - t0 < timeout:
            for r in self.grid.pull_messages(list(pending)):
                mid = r.metadata.reply_to_message_id
                pending.discard(mid)
                h = hosp_of_id.get(mid, "?")
                if r.has_error():
                    self.report("reply.error", **{"from": h}, kind=kind, error=str(r.error.reason))
                    continue
                payload = wire.check_reply(kind, json.loads(str(r.content["reply"]["json"])))
                replies[h] = payload
                self.report("reply.received", **{"from": h}, kind=kind, message_id=r.metadata.message_id, bytes=wire.size(payload), response=payload)
            time.sleep(0.25)
        return replies


def _legs(pairs: list[str], hosp: dict[str, str], closed: bool):
    seq = list(zip(pairs, pairs[1:] + pairs[:1])) if closed else list(zip(pairs, pairs[1:]))
    return [{"donor_pair": d, "donor_hospital": hosp.get(d, "alder"), "patient_pair": p, "patient_hospital": hosp[p]} for d, p in seq]


@app.main()
def main(grid: Grid, context: Context) -> None:
    rc = context.run_config
    phase, pace = str(rc.get("phase", "search")), float(rc["pace"])
    state_path = Path(str(rc.get("state-path", "")) or Path.home() / ".domino-state.json")
    report = Reporter(str(rc["bridge-url"]), "coordinator", context.run_id)
    state = json.loads(state_path.read_text()) if state_path.exists() and phase != "search" else {}
    c = Coord(grid, report, pace)
    report("run.start", phase=phase)
    c.hello()

    if phase == "search":
        prof = c.ask("profiles", {h: {"phase": "search"} for h in c.node_of})
        donors, hosp = [], {}
        for h, r in prof.items():
            for p in r["pairs"]:
                donors.append(p); hosp[p["pair"]] = h
        report("pool", pairs=sorted(hosp), hospitals=sorted(prof))
        comp = c.ask("compat", {h: {"donors": donors, "exclude": []} for h in c.node_of})
        edges = sorted({tuple(e) for r in comp.values() for e in r["edges"]})
        best = matching.best_cycles(sorted(hosp), set(edges), hosp)
        loop = list(best[0]) if best else []
        order = loop
        if len(loop) == 3 and (loop[1], loop[2]) not in set(edges):  # orient the loop donor -> patient
            order = [loop[0], loop[2], loop[1]]
        state = {"donors": donors, "hosp": hosp, "edges": edges, "plan": {"kind": "loop", "pairs": order}, "counter": len(order)}
        report("plan", kind="loop", legs=_legs(order, hosp, True), transplants=len(order), counter=len(order), edges=len(edges))

    elif phase == "approve":
        hosp, plan = state["hosp"], state["plan"]
        in_plan: dict[str, list[str]] = {}
        for p in plan["pairs"]:
            in_plan.setdefault(hosp[p], []).append(p)
        ans = c.ask("approve", {h: {"plan": plan["kind"], "pairs": ps, "surgery_date": SURGERY_DATE} for h, ps in in_plan.items()}, timeout=200)
        holds = [(h, a) for h, r in ans.items() for a in r["answers"] if a["decision"] == "hold"]
        if holds:
            h0, a0 = holds[0]
            others = {h: ps for h, ps in in_plan.items() if h != h0}
            report("hold.request", **{"from": h0}, pair=a0["pair"], hold_until=a0["hold_until"], reason=a0["reason"], to=sorted(others))
            hr = c.ask("hold", {h: {"plan": plan["kind"], "pairs": ps, "hold_until": a0["hold_until"], "from": h0} for h, ps in others.items()})
            consensus = all(r["decision"] == "accept" for r in hr.values()) and len(hr) == len(others)
            report("hold.result", consensus=consensus, replies={h: r for h, r in hr.items()})
            if not consensus:
                keep = [p for p in sorted(hosp) if p != a0["pair"]]
                best = matching.best_cycles(keep, {tuple(e) for e in state["edges"]}, hosp)
                swap = list(best[0]) if best else []
                state["plan"] = {"kind": "swap", "pairs": swap}
                state["held"] = a0["pair"]
                state["counter"] = len(swap)
                report("plan", kind="swap", legs=_legs(swap, hosp, True), transplants=len(swap), counter=len(swap), held=a0["pair"])
        else:
            report("plan", kind=plan["kind"], legs=_legs(plan["pairs"], hosp, True), transplants=len(plan["pairs"]), counter=len(plan["pairs"]), approved=True)

    elif phase == "chain":
        hosp = state["hosp"]
        used = set(state["plan"]["pairs"]) | ({state["held"]} if state.get("held") else set())
        stranger = json.loads(Path(str(rc["alder-pod"]), "stranger.json").read_text())
        report("chain.start", donor="the stranger", blood=stranger["donor_blood"], surgery_at="alder")
        pool = [d for d in state["donors"] if d["pair"] not in used] + [{k: stranger[k] for k in ("pair", "donor_blood", "donor_hla")}]
        comp = c.ask("compat", {h: {"donors": pool, "exclude": sorted(used)} for h in c.node_of})
        edges = {tuple(e) for r in comp.values() for e in r["edges"]}
        chain = matching.best_chain(sorted(p for p in hosp if p not in used), edges)
        before = state.get("counter", 0)
        hosp2 = dict(hosp, ALT="alder")
        report("plan", kind="chain", legs=_legs([matching.STRANGER] + chain, hosp2, False), transplants=len(chain),
               counter=before + len(chain), bridge_donor=chain[-1] if chain else None)
        state["chain"] = chain
        state["counter"] = before + len(chain)

    state_path.write_text(json.dumps(state))
    report("phase.end", phase=phase, ok=True)
