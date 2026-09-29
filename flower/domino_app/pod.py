"""The hospital's local patient data pod.  Only the directory given in this machine's node config is ever opened."""
from __future__ import annotations

import json
import re
from pathlib import Path


class Pod:
    def __init__(self, root: str, on_read=None):
        self.root = Path(root).expanduser().resolve()
        if not (self.root / "pairs.json").exists():
            raise FileNotFoundError(f"no pod at {self.root}")
        self.on_read = on_read or (lambda rel, detail: None)
        self.reads: list[str] = []

    def files(self) -> list[str]:
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file() and not p.name.startswith("."))

    def _read(self, rel: str) -> str:
        path = (self.root / rel).resolve()
        if self.root not in path.parents:  # never step outside this pod
            raise PermissionError(rel)
        self.reads.append(rel)
        return path.read_text(encoding="utf-8")

    def pairs(self) -> dict:
        data = json.loads(self._read("pairs.json"))
        self.on_read("pairs.json", f"{len(data['pairs'])} pair records")
        return data

    def note(self, rel: str) -> str:
        text = self._read(rel)
        self.on_read(rel, "availability note")
        return text

    def rulebook_sections(self) -> list[dict]:
        text = self._read("rulebook.md")
        title = text.splitlines()[0].lstrip("# ").strip()
        parts = re.split(r"^### ", text, flags=re.M)[1:]
        sections = []
        for part in parts:
            head, _, body = part.partition("\n")
            sec = head.split()[0]
            sections.append({"id": sec, "source": "rulebook", "title": head.strip(), "text": f"{head}\n{body.strip()}"})
        self.on_read("rulebook.md", f"{len(sections)} sections · {title}")
        return sections

    def documents(self) -> list[dict]:
        """Everything retrieval may search: availability notes and rulebook sections."""
        docs = []
        for rel in self.files():
            if rel.startswith("availability/"):
                docs.append({"id": rel, "source": "availability", "title": rel, "text": self.note(rel)})
        docs.extend(self.rulebook_sections())
        return docs
