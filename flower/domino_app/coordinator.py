"""Alder's side: build the screening form from Alder's own pod, and review the replies.  No Flower import."""
from __future__ import annotations

from . import screening, wire
from .pod import Pod
from .retrieval import Index

PAIR = "A1"
WINDOW = {"from": "2026-10-12", "to": "2026-10-23"}
QUESTIONS = [
    "Can one of your patients receive our donor's kidney? (blood type + crossmatch)",
    "Can that patient's donor give to our patient? (blood type + crossmatch)",
    "Is that pair ready in the proposed window? (your availability notes)",
    "Does your program's rulebook allow this exchange?",
]


def build_request(alder_pod: str, request_id: str, report) -> dict:
    pod = Pod(alder_pod, on_read=lambda rel, detail: report("pod.read", file=rel, detail=detail))
    pair = next(p for p in pod.pairs()["pairs"] if p["pair_id"] == PAIR)
    token = screening.candidate_token(request_id, "alder", PAIR)
    request = {
        "request_id": request_id,
        "from": "alder",
        "donor": {"token": token + "-D", "blood": pair["donor"]["blood"], "hla": pair["donor"]["hla"]},
        "patient": {"token": token + "-P", "blood": pair["patient"]["blood"],
                    "unacceptable_antigens": pair["patient"]["unacceptable_antigens"]},
        "window": WINDOW,
        "questions": QUESTIONS,
    }
    return wire.check_request(request)


def review(replies: dict[str, dict], alder_pod: str) -> dict:
    """Deterministic review of the restricted replies.  Proposes an exchange; a surgeon must still sign."""
    rules = Index(Pod(alder_pod).rulebook_sections()).search("exchange proposal reviewed surgeon signed approval", k=1)
    checks = []
    proposal = None
    for hospital, r in sorted(replies.items()):
        ok = r["candidate_found"] and r["readiness"] == "ready" and r["reason"] == "reciprocal_match"
        checks.append({"hospital": hospital, "candidate_found": r["candidate_found"], "readiness": r["readiness"],
                       "reason": r["reason"], "usable": ok})
        if ok and proposal is None:
            proposal = {
                "status": "proposed",
                "request_id": r["request_id"],
                "partner": hospital,
                "candidate_token": r["candidate_token"],
                "legs": [
                    {"from": "alder", "to": hospital, "what": "Alder's donor → partner's candidate patient"},
                    {"from": hospital, "to": "alder", "what": "partner's candidate donor → Alder's patient"},
                ],
                "requires": rules[0]["id"] if rules else "§2.4",
                "rule": rules[0]["text"] if rules else "",
            }
    return {"checks": checks, "proposal": proposal}
