"""The three-phase story: loop (3) -> hold, no consensus -> swap (2) -> stranger chain (+5 = 7)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flower"))
from domino_app import agent2, matching, wire  # noqa: E402

PODS = {h: str(ROOT / "pods" / h) for h in ("alder", "harbor", "riverbend")}
quiet = lambda *a, **k: None  # noqa: E731
advice_only = lambda **k: {"decision": k["advice"]["decision"], "hold_until": k["advice"].get("hold_until", "")}  # noqa: E731


def pool():
    prof = {h: wire.check_reply("profiles", agent2.profiles({}, d, h, quiet, 0)) for h, d in PODS.items()}
    donors = [p for r in prof.values() for p in r["pairs"]]
    hosp = {p["pair"]: h for h, r in prof.items() for p in r["pairs"]}
    return donors, hosp


def edges_for(donors, exclude=()):
    replies = {h: wire.check_reply("compat", agent2.compat({"donors": donors, "exclude": list(exclude)}, d, h, quiet, 0)) for h, d in PODS.items()}
    return {tuple(e) for r in replies.values() for e in r["edges"]}


def test_exactly_the_story_matches_and_none_inside_a_hospital():
    donors, hosp = pool()
    edges = edges_for(donors)
    assert edges == {("A1", "H1"), ("H1", "A1"), ("H1", "R1"), ("R1", "A1"), ("H2", "A2"), ("A2", "R2"), ("R2", "H3"), ("H3", "R3")}
    assert all(hosp[a] != hosp[b] for a, b in edges)


def test_loop_then_swap_without_riverbend():
    donors, hosp = pool()
    edges = edges_for(donors)
    assert matching.best_cycles(sorted(hosp), edges, hosp) == [("A1", "H1", "R1")]
    assert matching.best_cycles([p for p in sorted(hosp) if p != "R1"], edges, hosp) == [("A1", "H1")]


def test_riverbend_reads_the_scan_and_holds_for_infection():
    r = agent2.approve({"plan": "loop", "pairs": ["R1"], "surgery_date": "2026-10-02"}, PODS["riverbend"], "riverbend", quiet, advice_only, 0)
    assert r["answers"] == [{"pair": "R1", "decision": "hold", "readiness": "not_this_week", "reason": "infection", "hold_until": "2026-10-09"}]
    for h, pid in (("alder", "A1"), ("harbor", "H1")):
        a = agent2.approve({"plan": "loop", "pairs": [pid], "surgery_date": "2026-10-02"}, PODS[h], h, quiet, advice_only, 0)
        assert a["answers"][0]["decision"] == "approve"


def test_alder_can_wait_harbor_cannot():
    ask = {"plan": "loop", "hold_until": "2026-10-09", "from": "riverbend"}
    assert agent2.hold({**ask, "pairs": ["A1"]}, PODS["alder"], "alder", quiet, advice_only, 0) == {"decision": "accept", "reason": "none"}
    assert agent2.hold({**ask, "pairs": ["H1"]}, PODS["harbor"], "harbor", quiet, advice_only, 0) == {"decision": "decline", "reason": "donor_availability"}


def test_stranger_chain_adds_five():
    donors, hosp = pool()
    used = {"A1", "H1", "R1"}
    stranger = json.loads((ROOT / "pods/alder/stranger.json").read_text())
    rest = [d for d in donors if d["pair"] not in used] + [{k: stranger[k] for k in ("pair", "donor_blood", "donor_hla")}]
    chain = matching.best_chain(sorted(p for p in hosp if p not in used), edges_for(rest, used))
    assert chain == ["H2", "A2", "R2", "H3", "R3"]


def test_replies_carry_no_names():
    donors, _ = pool()
    text = json.dumps([agent2.compat({"donors": donors, "exclude": []}, d, h, quiet, 0) for h, d in PODS.items()])
    for h, d in PODS.items():
        for p in json.loads(Path(d, "pairs.json").read_text())["pairs"]:
            assert p["patient"]["name"].split()[0] not in text and p["donor"]["name"].split()[0] not in text
