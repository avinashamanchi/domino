"""Offline tests: screening, retrieval, wire format and the full agent flow for both hospitals."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flower"))

from domino_app import agent, coordinator, screening, wire  # noqa: E402
from domino_app.retrieval import Index  # noqa: E402

PODS = ROOT / "pods"
REQ_ID = "REQ-2026-0929-A1"


def quiet(*_a, **_k):
    pass


@pytest.fixture
def request_form():
    return coordinator.build_request(str(PODS / "alder"), REQ_ID, quiet)


def test_abo_rules():
    assert screening.abo_ok("O", "A") and screening.abo_ok("A", "AB")
    assert not screening.abo_ok("B", "A") and not screening.abo_ok("A", "O")


def test_request_carries_no_identity(request_form):
    text = json.dumps(request_form)
    for name in ("Maria", "Elena", "Alvarez", "sister"):
        assert name not in text
    assert request_form["donor"]["blood"] == "B" and request_form["patient"]["blood"] == "A"

def test_riverbend_one_way_and_widens_search(request_form):
    events = []
    resp = agent.handle_screen(request_form, str(PODS / "riverbend"), "riverbend", lambda t, **k: events.append((t, k)), pace=0)
    assert resp == {"request_id": REQ_ID, "candidate_token": "", "candidate_found": False,
                    "readiness": "searching_other_regions", "reason": "one_way_only"}
    outreach = next(k for t, k in events if t == "outreach")
    assert outreach["regions"] == ["Sierra Nevada (Reno)", "Central Valley (Fresno)", "Pacific Northwest (Portland)"]


def test_agent_reads_only_its_own_pod(request_form):
    events = []
    agent.handle_screen(request_form, str(PODS / "harbor"), "harbor", lambda t, **k: events.append((t, k)), pace=0)
    opened = next(k for t, k in events if t == "pod.open")
    assert opened["root"].endswith("pods/harbor")
    reads = next(k for t, k in events if t == "reply.ready")["pod_reads"]
    assert reads and all(not r.startswith("..") for r in reads)


def test_reply_never_contains_private_data(request_form):
    for h in ("harbor", "riverbend"):
        resp = agent.handle_screen(request_form, str(PODS / h), h, quiet, pace=0)
        text = json.dumps({k: v for k, v in resp.items() if k != "request_id"})  # the id is Alder's own
        pairs = json.loads((PODS / h / "pairs.json").read_text())["pairs"]
        for p in pairs:
            for field in (p["patient"]["name"], p["donor"]["name"], *p["donor"]["hla"], *p["patient"]["unacceptable_antigens"]):
                assert field not in text


@pytest.mark.parametrize("bad", [
    {"patient_name": "James"},
    {"notes": "on leave"},
    {"extra": 1},
])
def test_wire_rejects_extra_fields(bad):
    ok = {"request_id": REQ_ID, "candidate_token": "HP-ABC123", "candidate_found": True, "readiness": "ready", "reason": "reciprocal_match"}
    with pytest.raises(wire.WireError):
        wire.check_response({**ok, **bad})


def test_wire_rejects_free_text_categories():
    with pytest.raises(wire.WireError):
        wire.check_response({"request_id": REQ_ID, "candidate_token": "", "candidate_found": False,
                             "readiness": "James is not ready", "reason": "no_compatible_pair"})


def test_pod_cannot_escape_its_root():
    from domino_app.pod import Pod
    pod = Pod(str(PODS / "harbor"))
    with pytest.raises(PermissionError):
        pod._read("../riverbend/pairs.json")

def test_retrieval_finds_rule():
    idx = Index([{"id": "§1", "source": "r", "text": "donor work-up complete"}, {"id": "§2", "source": "r", "text": "implant timing 14:00"}])
    assert idx.search("work-up donor")[0]["id"] == "§1"
