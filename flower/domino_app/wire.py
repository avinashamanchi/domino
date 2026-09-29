"""What may cross between hospitals.  Checked in code on both ends of every Flower message."""
from __future__ import annotations

import json

READINESS = {"ready", "not_ready", "needs_review", "searching_other_regions", "not_applicable"}
REASONS = {"reciprocal_match", "one_way_only", "blood_type_incompatible", "crossmatch_positive",
           "donor_unavailable", "no_compatible_pair", "request_refused"}

# The restricted response: exactly these five fields, nothing else.
RESPONSE_FIELDS = ("request_id", "candidate_token", "candidate_found", "readiness", "reason")

REQUEST_FIELDS = {"request_id", "from", "donor", "patient", "window", "questions"}
REQUEST_DONOR = {"token", "blood", "hla"}
REQUEST_PATIENT = {"token", "blood", "unacceptable_antigens"}
FORBIDDEN_WORDS = ("name", "note", "chart", "age", "relation", "citation", "calendar")


class WireError(ValueError):
    pass


def _keys_only(obj: dict, allowed: set, where: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise WireError(f"{where}: field(s) not allowed on the wire: {sorted(extra)}")
    for k in obj:
        if any(w in k.lower() for w in FORBIDDEN_WORDS):
            raise WireError(f"{where}: forbidden field {k}")


def check_request(req: dict) -> dict:
    _keys_only(req, REQUEST_FIELDS, "request")
    _keys_only(req["donor"], REQUEST_DONOR, "request.donor")
    _keys_only(req["patient"], REQUEST_PATIENT, "request.patient")
    return req


def check_response(resp: dict) -> dict:
    if tuple(sorted(resp)) != tuple(sorted(RESPONSE_FIELDS)):
        raise WireError(f"response must have exactly {RESPONSE_FIELDS}, got {sorted(resp)}")
    if not isinstance(resp["candidate_found"], bool):
        raise WireError("candidate_found must be true/false")
    if resp["readiness"] not in READINESS:
        raise WireError(f"readiness not a category: {resp['readiness']}")
    if resp["reason"] not in REASONS:
        raise WireError(f"reason not a category: {resp['reason']}")
    token = resp["candidate_token"]
    if token and (not isinstance(token, str) or len(token) > 12):
        raise WireError("candidate_token must be a short opaque token")
    if resp["candidate_found"] != bool(token):
        raise WireError("candidate_token must be set exactly when candidate_found is true")
    return resp


def size(obj: dict) -> int:
    return len(json.dumps(obj, separators=(",", ":")).encode())


# ---------- three-phase story: profiles, compat, approve, hold ----------
PROFILE = {"pair", "donor_blood", "donor_hla"}
ANSWER = {"pair", "decision", "readiness", "reason", "hold_until"}
ASKS = {
    "profiles": {"phase"},
    "compat": {"donors", "exclude"},
    "approve": {"plan", "pairs", "surgery_date"},
    "hold": {"plan", "pairs", "hold_until", "from"},
}
REPLIES = {"profiles": {"pairs"}, "compat": {"edges"}, "approve": {"answers"}, "hold": {"decision", "reason"}}
DECISIONS = {"approve", "hold", "accept", "decline"}
REASONS2 = {"none", "infection", "donor_availability", "recipient_readiness", "or_capacity"}


def check_ask(kind: str, ask: dict) -> dict:
    _keys_only(ask, ASKS[kind], f"{kind} ask")
    for d in ask.get("donors", []):
        _keys_only(d, PROFILE, "donor profile")
    return ask


def check_reply(kind: str, reply: dict) -> dict:
    _keys_only(reply, REPLIES[kind], f"{kind} reply")
    for p in reply.get("pairs", []):
        _keys_only(p, PROFILE, "profile")
    for e in reply.get("edges", []):
        if not (isinstance(e, list) and len(e) == 2 and all(isinstance(x, str) and len(x) <= 4 for x in e)):
            raise WireError("edges must be [donor_pair, patient_pair] ids")
    for a in reply.get("answers", []):
        _keys_only(a, ANSWER, "approval")
        if a["decision"] not in DECISIONS or a["reason"] not in REASONS2 or a["readiness"] not in READINESS | {"not_this_week"}:
            raise WireError(f"approval must use categories: {a}")
    if kind == "hold" and (reply["decision"] not in DECISIONS or reply["reason"] not in REASONS2):
        raise WireError(f"hold reply must use categories: {reply}")
    return reply
