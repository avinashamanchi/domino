"""Build web/dist: self-contained pages (fonts, styles, jsQR, and a recorded real Flower run for REPLAY mode).

    python3 web/build.py            # uses web/recordings/*.jsonl if present
    python3 web/build.py --record   # first copy the latest runs/*.jsonl into web/recordings/
"""
import base64
import json
import shutil
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
SRC, DIST, REC = WEB / "src", WEB / "dist", WEB / "recordings"
FACES = [
    ("Ubuntu", 400, "normal", "ubuntu-latin-400-normal.woff2"),
    ("Ubuntu", 400, "italic", "ubuntu-latin-400-italic.woff2"),
    ("Ubuntu", 500, "normal", "ubuntu-latin-500-normal.woff2"),
    ("Ubuntu", 700, "normal", "ubuntu-latin-700-normal.woff2"),
    ("Ubuntu Condensed", 400, "normal", "ubuntu-condensed-latin-400-normal.woff2"),
    ("Ubuntu Mono", 400, "normal", "ubuntu-mono-latin-400-normal.woff2"),
]


def fonts() -> str:
    return "\n".join(
        f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:{w};font-display:block;"
        f"src:url(data:font/woff2;base64,{base64.b64encode((WEB / 'fonts' / f).read_bytes()).decode()}) format('woff2');}}"
        for fam, w, style, f in FACES)


def latest(prefix: str) -> Path | None:
    runs = sorted((ROOT / "runs").glob(f"{prefix}-*.jsonl"))
    return runs[-1] if runs else None


def load_recording(prefix: str) -> dict | None:
    path = REC / f"{prefix}.jsonl"
    if not path.exists():
        return None
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    # keep only the last complete run in the file
    run_id = next((e.get("run_id") for e in reversed(events) if e.get("run_id") and e.get("type") in ("run.end", "reply.ready")), None)
    last = max((j for j, e in enumerate(events) if e.get("run_id") == run_id), default=0)
    launches = [i for i, e in enumerate(events) if e.get("type") == "launch" and i < last]
    start = launches[-1] if launches else 0
    events = [e for e in events[start:last + 1] if e.get("run_id") in (None, run_id)]
    return {"run_id": run_id, "events": events}


def fill(html: str, **parts) -> str:
    for k, v in parts.items():
        marker = f"/*@{k}@*/"
        assert marker in html, marker
        html = html.replace(marker, v)
    return html


def main():
    if "--record" in sys.argv:
        REC.mkdir(exist_ok=True)
        for prefix in ("alder", "harbor", "riverbend"):
            src = latest(prefix)
            if src:
                shutil.copy(src, REC / f"{prefix}.jsonl")
                print(f"recorded {src.name} -> web/recordings/{prefix}.jsonl")
    DIST.mkdir(exist_ok=True)
    common = {"FONTS": fonts(), "SHARED": (SRC / "shared.css").read_text(), "SOURCE": (SRC / "source.js").read_text()}
    alder = load_recording("alder")
    if alder:  # replay only the coordinator's run, not UI clicks from that session
        alder["events"] = [e for e in alder["events"] if e.get("who") in ("coordinator", "bridge", "flwr")]
    projector = fill((SRC / "projector.html").read_text(), **common,
                     JSQR=(WEB / "vendor" / "jsQR.js").read_text(), RECORDING=json.dumps(alder))
    recs = {h: r for h in ("harbor", "riverbend") if (r := load_recording(h))}
    console = fill((SRC / "console.html").read_text(), **common, RECORDINGS=json.dumps(recs))
    outputs = {
        "projector.html": projector,
        "console.html": console,
        # Offline copies: open these straight from disk on any machine (REPLAY mode).
        "A-alder-projector.html": projector,
        "B-harbor-console.html": console.replace("<script>/*", "<script>window.DEFAULT_HOSPITAL='harbor';/*", 1),
        "C-riverbend-console.html": console.replace("<script>/*", "<script>window.DEFAULT_HOSPITAL='riverbend';/*", 1),
    }
    for name, html in outputs.items():
        (DIST / name).write_text(html)
        print(f"web/dist/{name}  {len(html) // 1024} KB")
    forms = ROOT / "approval-forms"
    if forms.exists():
        for png in forms.glob("*.png"):
            shutil.copy(png, DIST / png.name)


if __name__ == "__main__":
    main()
