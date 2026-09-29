# Domino: kidney-exchange screening across hospitals, with Flower

Alder Medical Center (San Jose) has a patient, Maria, whose sister Elena wants to donate, but their blood types don't match. Harbor Point Hospital (Oakland) and Riverbend General (Sacramento) each keep their own patients in a private **data pod**.

Alder's coordinator sends **one screening form** to both hospitals over **Flower**. Each hospital's agent fills the form from its own pod and returns a **five-field reply**.

- Harbor Point finds a reciprocal candidate (James and Priya).
- Riverbend finds none, and its rulebook tells it to widen the search to partner regions.

A surgeon then reviews a signed approval form, and the exchange goes from **Proposed** to **Reviewed**.

All patients, donors and hospitals are fictional. The data is synthetic and hardcoded.

## What runs where

| Machine | Processes | Reads |
| --- | --- | --- |
| **A · Alder** (projector) | Flower **SuperLink**, the coordinator **ServerApp** (`domino_app/server_app.py`), and the projector bridge | `pods/alder` only |
| **B · Harbor Point** | Flower **SuperNode**, the hospital agent **ClientApp** (`domino_app/client_app.py`), and the private console bridge | `pods/harbor` only |
| **C · Riverbend** | Flower **SuperNode**, the same ClientApp, and the private console bridge | `pods/riverbend` only |

- **Between machines, the only channel is Flower.** The coordinator pushes `query.hello` and `query.screen` messages; the SuperNodes reply.
- **Each bridge binds to `127.0.0.1`.** It shows only its own machine's events, so a hospital console can't be opened from another machine.
- **Each hospital's pod path is set in its SuperNode's `--node-config`.** It never crosses the network. `Pod` refuses to read outside that directory.

## The data pods (`pods/<hospital>/`)

- `pairs.json`: synthetic patient–donor pairs (blood type, donor HLA, patient unacceptable antigens).
- `availability/*.md`: donor availability notes, each with an `available_from / available_to / workup` header.
- `rulebook.md`: one program rulebook, with `### §` sections.

## What the agents do

**Coordinator (A):**
- Reads Alder's pod.
- Builds the form: tokens, blood types, donor HLA, recipient unacceptable antigens, window, and 4 questions. No names or charts.
- Sends the form, collects the replies, and reviews them in code.

**Hospital agent (B, C)**, all on that hospital's machine:
1. **Receive** the form (Flower message).
2. **Open its own pod.** The console shows every file it reads.
3. **Retrieve** with BM25 over its pair records, notes and rulebook sections.
4. **Screen in code.** ABO compatibility and virtual crossmatch, in both directions, for every pair (`screening.py`).
5. **Decide.** If there's a match, check readiness from the availability note and rulebook §1.1–1.2. If there isn't, look up what the rulebook says to do next. Riverbend's §3.1 names its partner regions: Reno, Fresno, Portland. That outreach is **illustrative**: those regions are not in this Flower network, and the screens say so.
6. **Reply** with exactly `request_id, candidate_token, candidate_found, readiness, reason`, checked against the allowlist in `wire.py` on both ends.

- The candidate token is an opaque hash, so Alder never learns who the candidate is.
- `reason` and `readiness` come from fixed category lists.

**Doctor review (A, Step 3):**
- Drop `approval-forms/approval-signed.png` on the page.
- The page decodes the form's QR code (jsQR) to extract its fields and locate the signature and decision boxes.
- It then measures the ink in those boxes and checks the request ID and candidate token against the live run.
- **Confirm approval** unlocks only when every check passes and the surgeon ticks the acknowledgement.
- Two failing samples are included: `approval-unsigned.png` and `approval-wrong-candidate.png`.

## How to run the demo

One-time setup on every Mac. Python 3.11 and [uv](https://docs.astral.sh/uv/) are required.

```bash
cd domino-demo/flower && uv venv --python 3.11 && uv pip install "flwr>=1.22,<2.0"
```

**Mac A (Alder, projector):**

```bash
scripts/run-alder.sh
```

- It prints the IP address the hospitals should connect to.
- Open <http://127.0.0.1:8765/projector.html> in full screen.

**Mac B (Harbor Point):**

```bash
scripts/run-hospital.sh harbor <alder-ip>
```

Then open <http://127.0.0.1:8766/console.html>.

**Mac C (Riverbend):**

```bash
scripts/run-hospital.sh riverbend <alder-ip>
```

Then open <http://127.0.0.1:8767/console.html>.

- A's Wi-Fi must allow inbound connections on port 9092 (the SuperLink Fleet API).
- On Macs B and C, copy only that hospital's pod, and set `DOMINO_POD=/path/to/pod` if it lives elsewhere.

**Rehearsing on one Mac:** `scripts/run-all-local.sh` starts all of it.

**Stopping:** Ctrl+C, or `scripts/stop.sh` to clear anything left running. The launch scripts refuse to start while a port is still in use, and tell you to run `scripts/stop.sh`.

**No network at all:** open `web/dist/A-alder-projector.html`, `B-harbor-console.html` or `C-riverbend-console.html` from disk. They play a **recorded real Flower run** (run `13554069240519904883`), and the badge reads **REPLAY** instead of **LIVE**.

### Projector keys

| Key | Action |
| --- | --- |
| → / Space | next. On "The network", this starts the Flower run, the same as clicking **Find an exchange**. |
| ← | back |
| L | Flower run log: run ID, message IDs, every event, and `flwr` output |
| H | help |
| F | fullscreen |
| R | reset the story |

### Run of show

1. **The situation:** Maria and Elena, then James and Priya, then one statistic.
2. **The question:** "What if the person who could help your patient is at another hospital?"
3. **The network:** three hospitals, three private pods. Click **Find an exchange**.
4. **Step 1 · Ask:** the form flies to both SuperNodes, and each lane steps through its flowchart. Turn Macs B and C toward the judges: their consoles show the real steps inside each pod. The reply forms fill in: **Candidate found** and **No candidate found**. Riverbend widens its search.
5. **Step 2 · Review:** the replies are shown as a form, followed by Alder's review in code. The map draws the reciprocal Alder ↔ Harbor Point exchange as **PROPOSED**.
6. **Step 3 · Doctor review:** drop the signed form. The page shows the extracted fields and passing checks. Tick the box and click **Confirm approval**. The map turns **REVIEWED**.

## Statistic

"95,492 people in the U.S. are waiting for a kidney" is attributed to organdonor.gov (HRSA), waiting-list data as of July 30, 2026. It was found via search results citing that page; organdonor.gov itself blocked a direct fetch. Please open the page and confirm the number before presenting.

## Development

- Tests (offline, no Flower needed): `uvx --python 3.11 pytest -q tests`
- Rebuild the pages: `python3 web/build.py`
- Record the latest run for REPLAY mode: `python3 web/build.py --record`
- Regenerate the approval forms: `uv run --python 3.11 --with pillow --with segno python tools/make_approval_forms.py`
- The first static prototype is kept in `v1-static/`.

### Flower notes (1.39)

- `flwr run` targets a connection named in `$FLWR_HOME/config.toml`. The scripts write `[superlink.domino-local] address = "127.0.0.1:8000"`: the Control API is HTTP on port 8000.
- The SuperLink is started with `--disable-runtime-dependency-installation`. Otherwise every run spends minutes on `uv sync` building a fresh environment.
- `flwr run` ships the app to the SuperNodes as a FAB. `fab-include` limits it to `domino_app/**/*.py`, so no pod data is ever in the bundle.
