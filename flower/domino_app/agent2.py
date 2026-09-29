"""Hospital agent for the three-phase story: profiles, compat, approve (with a person), hold.

Pure Python (no Flower import). `report` shows each step on this hospital's own screen; `decide` asks this
hospital's person (console) and returns their choice, or the agent's advice when the countdown runs out.
"""
from __future__ import annotations

import re
import time
from datetime import date, timedelta

from . import screening
from .pod import Pod
from .retrieval import Index

INFECTION = re.compile(r"pneumonia|iv antibiotic|ceftriaxone|fever|(?<!a)febrile", re.I)


def _pod(pod_dir, report):
    return Pod(pod_dir, on_read=lambda rel, detail: report("pod.read", file=rel, detail=detail))


def profiles(req, pod_dir, hospital, report, pace=1.0):
    pod = _pod(pod_dir, report)
    report("pod.open", root=str(pod.root), files=pod.files())
    time.sleep(0.8 * pace)
    pairs = pod.pairs()["pairs"]
    out = [{"pair": p["pair_id"], "donor_blood": p["donor"]["blood"], "donor_hla": p["donor"]["hla"]} for p in pairs]
    report("profiles", count=len(out), pairs=[{"pair": p["pair_id"], "patient": p["patient"]["name"].split()[0], "donor": p["donor"]["name"].split()[0],
                                              "patient_blood": p["patient"]["blood"], "donor_blood": p["donor"]["blood"]} for p in pairs])
    time.sleep(0.8 * pace)
    return {"pairs": out}


def compat(req, pod_dir, hospital, report, pace=1.0):
    pod = _pod(pod_dir, report)
    pairs = [p for p in pod.pairs()["pairs"] if p["pair_id"] not in set(req.get("exclude", []))]
    time.sleep(0.6 * pace)
    rows, edges = [], []
    for p in pairs:
        for d in req["donors"]:
            if d["pair"] == p["pair_id"]:
                continue
            c = screening.check(d["donor_blood"], d["donor_hla"], p["patient"]["blood"], p["patient"]["unacceptable_antigens"])
            if c["ok"]:
                edges.append([d["pair"], p["pair_id"]])
            rows.append({"donor": d["pair"], "patient": p["pair_id"], "patient_name": p["patient"]["name"].split()[0], **c})
    report("screen", checked=len(rows), matches=[r for r in rows if r["ok"]],
           donors=len(req["donors"]), patients=len(pairs), stranger=any(d["pair"] == "ALT" for d in req["donors"]))
    time.sleep(1.0 * pace)
    return {"edges": edges}


def _note(pod, rel):
    text = pod.note(rel)
    return text, screening.parse_note_header(text)


def approve(req, pod_dir, hospital, report, decide, pace=1.0):
    """Readiness for our pair(s) on the surgery date, then a person decides."""
    pod = _pod(pod_dir, report)
    rules = Index(pod.rulebook_sections())
    day = req["surgery_date"]
    results = []
    for pid in req["pairs"]:
        pair = next(p for p in pod.pairs()["pairs"] if p["pair_id"] == pid)
        time.sleep(0.6 * pace)
        # New scans land in the pod's inbox; the agent reads them here, on this machine.
        for rel in [f for f in pod.files() if f.startswith(f"inbox/{pid}_")]:
            report("scan.arrived", pair=pid, file=rel, patient=pair["patient"]["name"].split()[0])
            time.sleep(0.8 * pace)
        notes = [f for f in pod.files() if (f.startswith(f"charts/{pid}_") or f.startswith(f"inbox/{pid}_"))]
        texts = {rel: pod.note(rel) for rel in notes}
        time.sleep(0.6 * pace)
        infected = {rel: t for rel, t in texts.items() if INFECTION.search(t)}
        hits = rules.search(" ".join(infected.values()) if infected else "recipient active waiting list donor work-up", k=2)
        report("retrieve", purpose="Which of our rules apply?", hits=[{"id": h["id"], "title": h["title"]} for h in hits])
        time.sleep(0.8 * pace)
        donor_note = next((f for f in pod.files() if f.startswith(f"availability/{pid}_")), None)
        header = _note(pod, donor_note)[1] if donor_note else {}
        donor_ok = bool(header) and header["available_from"] <= day <= header["available_to"]
        if infected:
            rel, text = next(iter(infected.items()))
            scan_day = re.search(r"(\d{4}-\d{2}-\d{2})", text).group(1)
            hold_until = (date.fromisoformat(scan_day) + timedelta(days=10)).isoformat()
            quote = next((ln for ln in text.splitlines() if INFECTION.search(ln)), "")
            advice = {"decision": "hold", "readiness": "not_this_week", "reason": "infection", "hold_until": hold_until,
                      "why": quote, "source": rel, "rule": next((h["id"] for h in hits if "infection" in h["title"].lower()), hits[0]["id"])}
        elif not donor_ok:
            advice = {"decision": "hold", "readiness": "not_this_week", "reason": "donor_availability", "hold_until": "",
                      "why": f"Donor free {header.get('available_from')}–{header.get('available_to')}", "source": donor_note, "rule": ""}
        else:
            advice = {"decision": "approve", "readiness": "ready", "reason": "none", "hold_until": "",
                      "why": f"{pair['donor']['name'].split()[0]} free until {header['available_to']} · chart clear", "source": donor_note, "rule": ""}
        report("advice", pair=pid, patient=pair["patient"]["name"].split()[0], donor=pair["donor"]["name"].split()[0], **advice)
        choice = decide(kind="approve", pair=pid, advice=advice, patient=pair["patient"]["name"].split()[0], day=day)
        results.append({"pair": pid, "decision": choice["decision"], "readiness": advice["readiness"],
                        "reason": advice["reason"] if choice["decision"] != "approve" else "none",
                        "hold_until": choice.get("hold_until", "") if choice["decision"] == "hold" else ""})
    return {"answers": results}


def hold(req, pod_dir, hospital, report, decide, pace=1.0):
    """Another hospital asks everyone to wait. Can our donors still give on the new date?"""
    pod = _pod(pod_dir, report)
    until = req["hold_until"]
    time.sleep(0.6 * pace)
    worst = None
    for pid in req["pairs"]:
        pair = next(p for p in pod.pairs()["pairs"] if p["pair_id"] == pid)
        rel = next((f for f in pod.files() if f.startswith(f"availability/{pid}_")), None)
        text, header = _note(pod, rel)
        time.sleep(0.8 * pace)
        ok = header["available_to"] >= until
        quote = next((ln for ln in text.splitlines() if ln and not ln.startswith("#") and ":" not in ln[:16]), "")
        report("availability", pair=pid, donor=pair["donor"]["name"].split()[0], available_to=header["available_to"], hold_until=until, ok=ok, quote=quote, source=rel)
        time.sleep(0.8 * pace)
        if not ok:
            worst = {"decision": "decline", "reason": "donor_availability", "why": quote}
    advice = worst or {"decision": "accept", "reason": "none", "why": "All our donors can wait."}
    report("advice", kind="hold", **advice, hold_until=until)
    choice = decide(kind="hold", pair=",".join(req["pairs"]), advice=advice, day=until)
    return {"decision": choice["decision"], "reason": advice["reason"] if choice["decision"] == "decline" else "none"}
