"""Deterministic screening: blood type, virtual crossmatch, readiness.  Code decides, nothing else does."""
from __future__ import annotations

import hashlib
from datetime import date

# donor blood type -> recipient blood types it can give to
ABO = {"O": {"O", "A", "B", "AB"}, "A": {"A", "AB"}, "B": {"B", "AB"}, "AB": {"AB"}}


def abo_ok(donor_blood: str, patient_blood: str) -> bool:
    return patient_blood in ABO[donor_blood]


def crossmatch_conflicts(donor_hla: list[str], unacceptable: list[str]) -> list[str]:
    """Donor antigens the patient has antibodies against (virtual crossmatch)."""
    bad = set(unacceptable)
    return [a for a in donor_hla if a in bad]


def check(donor_blood: str, donor_hla: list[str], patient_blood: str, unacceptable: list[str]) -> dict:
    abo = abo_ok(donor_blood, patient_blood)
    conflicts = crossmatch_conflicts(donor_hla, unacceptable)
    return {"abo": abo, "crossmatch": not conflicts, "conflicts": conflicts, "ok": abo and not conflicts}


def screen_pairs(request: dict, pairs: list[dict]) -> list[dict]:
    """For every local pair, check both directions of a reciprocal exchange with the requesting pair.

    give:    requester's donor  -> our patient
    receive: our donor          -> requester's patient
    """
    rd, rp = request["donor"], request["patient"]
    rows = []
    for p in pairs:
        give = check(rd["blood"], rd["hla"], p["patient"]["blood"], p["patient"]["unacceptable_antigens"])
        receive = check(p["donor"]["blood"], p["donor"]["hla"], rp["blood"], rp["unacceptable_antigens"])
        rows.append({"pair_id": p["pair_id"], "give": give, "receive": receive, "reciprocal": give["ok"] and receive["ok"]})
    return rows


def parse_note_header(text: str) -> dict:
    """Availability notes start with `key: value` lines (available_from, available_to, workup)."""
    out = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith("#"):
            key, _, value = line.partition(":")
            key = key.strip()
            if key in {"available_from", "available_to", "workup"}:
                out[key] = value.strip()
        if not line.strip() and out:
            break
    return out


def readiness(note: dict, window_from: str, window_to: str, list_status: str, today: str) -> dict:
    """Ready if the donor window overlaps the proposed window, work-up is complete and < 12 months old,
    and the recipient is active (rulebook §1.1, §1.2)."""
    a0, a1 = date.fromisoformat(note["available_from"]), date.fromisoformat(note["available_to"])
    w0, w1 = date.fromisoformat(window_from), date.fromisoformat(window_to)
    overlap = a0 <= w1 and w0 <= a1
    workup_done = note.get("workup", "").startswith("complete")
    workup_date = date.fromisoformat(note["workup"].split()[-1]) if workup_done else None
    workup_fresh = bool(workup_date) and (date.fromisoformat(today) - workup_date).days < 365
    active = list_status == "active"
    checks = {"window_overlap": overlap, "workup_complete": workup_done and workup_fresh, "recipient_active": active}
    status = "ready" if all(checks.values()) else ("not_ready" if not overlap else "needs_review")
    return {"status": status, "checks": checks,
            "overlap": [max(a0, w0).isoformat(), min(a1, w1).isoformat()] if overlap else None}


def candidate_token(request_id: str, hospital: str, pair_id: str) -> str:
    """Opaque, deterministic token: the requester can refer to the candidate without learning who it is."""
    prefix = {"alder": "AL", "harbor": "HP", "riverbend": "RB"}.get(hospital, "XX")
    digest = hashlib.sha256(f"{request_id}:{hospital}:{pair_id}:domino".encode()).hexdigest()[:6].upper()
    return f"{prefix}-{digest}"
