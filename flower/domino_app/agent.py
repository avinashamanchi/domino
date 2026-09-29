"""A hospital's local agent: fills Alder's screening form from its own pod and returns the restricted reply.

Pure Python, no Flower import, so it can be tested offline.  `report` shows each step on this hospital's
own screen; `pace` slows the steps down so people can follow them.
"""
from __future__ import annotations

import re
import time

from . import screening, wire
from .pod import Pod
from .retrieval import Index

TODAY = "2026-09-29"


def pair_text(p: dict) -> str:
    pt, dn = p["patient"], p["donor"]
    return (f"Pair {p['pair_id']}. Patient blood type {pt['blood']} (patient_blood_{pt['blood'].lower()}), "
            f"{pt['list_status']} on the list, {len(pt['unacceptable_antigens'])} unacceptable antigens. "
            f"Donor blood type {dn['blood']} (donor_blood_{dn['blood'].lower()}).")


def handle_screen(request: dict, pod_dir: str, hospital: str, report, pace: float = 1.0) -> dict:
    wait = lambda s: time.sleep(max(0.0, s * pace))  # noqa: E731
    wire.check_request(request)
    report("form.received", request=request, bytes=wire.size(request))
    wait(1.0)

    # 1 · Open this hospital's pod: the only data this agent can reach.
    pod = Pod(pod_dir, on_read=lambda rel, detail: report("pod.read", file=rel, detail=detail))
    report("pod.open", root=str(pod.root), files=pod.files())
    wait(0.9)
    data = pod.pairs()
    pairs = data["pairs"]
    wait(0.7)

    # 2 · Retrieve: which of our pairs, notes and rules are relevant to this form?
    rd, rp = request["donor"], request["patient"]
    can_receive = sorted(screening.ABO[rd["blood"]])
    can_give = sorted(t for t in screening.ABO if rp["blood"] in screening.ABO[t])
    docs = [{"id": p["pair_id"], "source": "pairs", "title": f"pair {p['pair_id']}", "text": pair_text(p)} for p in pairs]
    docs += pod.documents()
    index = Index(docs)
    q1 = " ".join([f"patient_blood_{t.lower()}" for t in can_receive] + [f"donor_blood_{t.lower()}" for t in can_give] + ["active"])
    hits = index.search(q1, k=4, source="pairs")
    report("retrieve", purpose="Which of our pairs could fit this form?", query=q1,
           hits=[{"id": h["id"], "score": h["score"], "matched": h["matched"], "text": h["text"]} for h in hits],
           searched=len(pairs))
    wait(1.1)

    # 3 · Screen every pair in code, both directions (blood type + virtual crossmatch).
    rows = screening.screen_pairs(request, pairs)
    by_id = {p["pair_id"]: p for p in pairs}
    report("screen", request_donor_blood=rd["blood"], request_patient_blood=rp["blood"], rows=[{
        **r, "patient_initials": by_id[r["pair_id"]]["patient"]["initials"],
        "patient_name": by_id[r["pair_id"]]["patient"]["name"].split()[0],
        "donor_name": by_id[r["pair_id"]]["donor"]["name"].split()[0],
        "patient_blood": by_id[r["pair_id"]]["patient"]["blood"],
        "donor_initials": by_id[r["pair_id"]]["donor"]["initials"],
        "donor_blood": by_id[r["pair_id"]]["donor"]["blood"],
    } for r in rows])
    wait(1.3)

    matches = [r for r in rows if r["reciprocal"]]
    if matches:
        m = matches[0]
        pair = by_id[m["pair_id"]]
        # 4 · Readiness from this pair's availability note and the program rulebook.
        rule_hits = index.search("donor work-up complete recipient active waiting list exchange approval", k=3, source="rulebook")
        report("retrieve", purpose="Which of our rules decide readiness?",
               query="donor work-up complete recipient active waiting list exchange approval",
               hits=[{"id": h["id"], "score": h["score"], "matched": h["matched"], "text": h["text"]} for h in rule_hits],
               searched=sum(1 for d in docs if d["source"] == "rulebook"))
        wait(0.9)
        note_rel = next((f for f in pod.files() if f.startswith(f"availability/{m['pair_id']}_")), None)
        note_text = pod.note(note_rel) if note_rel else ""
        header = screening.parse_note_header(note_text)
        ready = screening.readiness(header, request["window"]["from"], request["window"]["to"],
                                    pair["patient"]["list_status"], TODAY)
        report("readiness", pair_id=m["pair_id"], note=note_rel, header=header, window=request["window"], **ready,
               quote=next((ln for ln in note_text.splitlines() if "leave" in ln.lower() or "available" in ln.lower() and ":" not in ln), ""),
               rules=[h["id"] for h in rule_hits])
        wait(1.1)
        response = {
            "request_id": request["request_id"],
            "candidate_token": screening.candidate_token(request["request_id"], hospital, m["pair_id"]),
            "candidate_found": True,
            "readiness": ready["status"],
            "reason": "reciprocal_match",
        }
    else:
        give_ok = any(r["give"]["ok"] for r in rows)
        receive_ok = any(r["receive"]["ok"] for r in rows)
        abo_any = any(r["give"]["abo"] and r["receive"]["abo"] for r in rows)
        reason = ("one_way_only" if give_ok or receive_ok
                  else "crossmatch_positive" if abo_any else "blood_type_incompatible")
        report("decision", candidate_found=False, reason=reason,
               detail=("We have a donor who could help Alder's patient, but none of our patients can receive "
                       "Alder's donor." if receive_ok and not give_ok else
                       "One direction works, the other does not." if reason == "one_way_only" else
                       "No pair passes both blood type and crossmatch."))
        wait(1.0)
        # 5 · No local match: does our rulebook let us widen the search?
        q = "no reciprocal match forward partner regions third pair loop"
        rule_hits = index.search(q, k=2, source="rulebook")
        report("retrieve", purpose="What does our rulebook say when there is no local match?", query=q,
               hits=[{"id": h["id"], "score": h["score"], "matched": h["matched"], "text": h["text"]} for h in rule_hits],
               searched=sum(1 for d in docs if d["source"] == "rulebook"))
        wait(1.0)
        rule = next((h for h in rule_hits if "partner regions" in h["text"].lower()), None)
        readiness = "not_applicable"
        if rule:
            m = re.search(r"Partner regions[^:]*:\s*(.+?)\.\s*$", rule["text"], flags=re.S)
            regions = [r.strip() for r in m.group(1).split(";")] if m else []
            readiness = "searching_other_regions"
            report("outreach", rule=rule["id"], regions=regions,
                   note="Illustrative: partner regions are outside this demo's Flower network.")
            wait(1.2)
        response = {
            "request_id": request["request_id"],
            "candidate_token": "",
            "candidate_found": False,
            "readiness": readiness,
            "reason": reason,
        }

    wire.check_response(response)
    report("reply.ready", response=response, bytes=wire.size(response), fields=list(wire.RESPONSE_FIELDS),
           pod_reads=pod.reads)
    return response
