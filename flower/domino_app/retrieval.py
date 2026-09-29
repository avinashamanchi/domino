"""Tiny BM25 over one hospital's own pod (pair records, availability notes, rulebook sections)."""
from __future__ import annotations

import math
import re
from collections import Counter

STOP = set("a an the of for to and or in on at is are be with from by as this that it its no not our any may".split())
TOKEN = re.compile(r"[a-z0-9_§.]+")


def tokens(text: str) -> list[str]:
    out = []
    for t in TOKEN.findall(text.lower()):
        t = t.strip(".")
        if t and t not in STOP and (len(t) > 1 or t in {"a", "b", "o"}):
            out.append(t)
    return out


class Index:
    def __init__(self, docs: list[dict], k1: float = 1.4, b: float = 0.75):
        """docs: [{"id", "source", "text"}]"""
        self.docs, self.k1, self.b = docs, k1, b
        self.toks = [tokens(d["text"]) for d in docs]
        self.tf = [Counter(t) for t in self.toks]
        self.avgdl = sum(len(t) for t in self.toks) / max(1, len(self.toks))
        self.df = Counter(t for ts in self.toks for t in set(ts))

    def search(self, query: str, k: int = 3, source: str | None = None) -> list[dict]:
        q = list(dict.fromkeys(tokens(query)))
        n = len(self.docs)
        hits = []
        for i, doc in enumerate(self.docs):
            if source and doc["source"] != source:
                continue
            score, matched = 0.0, []
            for t in q:
                f = self.tf[i].get(t, 0)
                if not f:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                score += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(self.toks[i]) / self.avgdl))
                matched.append(t)
            if score > 0:
                hits.append({**doc, "score": round(score, 3), "matched": matched})
        return sorted(hits, key=lambda h: -h["score"])[:k]
