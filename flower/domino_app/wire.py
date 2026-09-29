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
