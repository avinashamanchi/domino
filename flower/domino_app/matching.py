"""Exchange matching: disjoint 2- and 3-cycles, and the longest chain from a stranger's (altruistic) kidney.

Pure code. Pairs are identified by pair id ("A1") and hospital; edges are (donor_pair, patient_pair) meaning
"the donor of donor_pair can give to the patient of patient_pair".
"""
from __future__ import annotations

from itertools import combinations

STRANGER = "ALT"


def cycles(pairs: list[str], edges: set[tuple[str, str]]) -> list[tuple[str, ...]]:
    out = []
    for a, b in combinations(pairs, 2):
        if (a, b) in edges and (b, a) in edges:
            out.append((a, b))
    for a in pairs:
        for b in pairs:
            for c in pairs:
                if len({a, b, c}) == 3 and a == min(a, b, c) and (a, b) in edges and (b, c) in edges and (c, a) in edges:
                    out.append((a, b, c))
    return out


def best_cycles(pairs: list[str], edges: set[tuple[str, str]], hospital_of: dict[str, str]) -> list[tuple[str, ...]]:
    """Maximize transplants with disjoint cycles; tie-break: more hospitals involved, then lexicographic."""
    cs = cycles(pairs, edges)
    best, best_key = [], (0, 0, ())
    def search(i, chosen, used):
        nonlocal best, best_key
        if i == len(cs):
            key = (sum(len(c) for c in chosen), len({hospital_of[p] for c in chosen for p in c}), tuple(sorted(chosen)))
            if (key[0], key[1]) > (best_key[0], best_key[1]) or ((key[0], key[1]) == (best_key[0], best_key[1]) and key[2] < best_key[2]):
                best, best_key = list(chosen), key
            return
        search(i + 1, chosen, used)
        if not used & set(cs[i]):
            search(i + 1, chosen + [cs[i]], used | set(cs[i]))
    search(0, [], set())
    return best


def legs_of_cycle(c: tuple[str, ...]) -> list[tuple[str, str]]:
    return [(c[i], c[(i + 1) % len(c)]) for i in range(len(c))]


def best_chain(pairs: list[str], edges: set[tuple[str, str]], start: str = STRANGER) -> list[str]:
    """Longest simple path start -> p1 -> p2 ...; each step gives a kidney to that pair's patient."""
    best: list[str] = []
    def dfs(node, path):
        nonlocal best
        if len(path) > len(best) or (len(path) == len(best) and path < best):
            best = list(path)
        for p in pairs:
            if p not in path and (node, p) in edges:
                dfs(p, path + [p])
    dfs(start, [])
    return best
