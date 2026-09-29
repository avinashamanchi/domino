# Domino: three-page demo

Three standalone web pages. Fonts, styles and scripts are inlined, so they need no internet connection.

| File | Runs on | What it shows |
| --- | --- | --- |
| `dist/A-coordinator-alder.html` | projector Mac | Slideshow: 1) standby stats and the question, 2) route map Oakland → San Jose, 3) signature check with computer vision and surgeon approval |
| `dist/B-harbor-point.html` | hospital Mac #2 | Harbor Point's private agent: retrieval over its own records, answers **YES** |
| `dist/C-riverbend.html` | hospital Mac #3 | Riverbend's private agent: same agent, its own records, answers **NO** |

## How to run the demo

1. On the projector Mac, run `python3 relay.py` (standard library only). It prints the three URLs, for example `http://192.168.1.20:8765/B-harbor-point.html`.
2. Open A on the projector and B and C on the other Macs, using those URLs. All Macs must be on the same Wi-Fi or hotspot.
   - If you copied the files to the other Macs instead, open each one and add `?relay=192.168.1.20:8765` to the end of its address. You can also use the **Connect to relay** button in the footer.
3. Check that the badge on A reads `LIVE · relay … · 2/2 hospital agents online`, and that B and C read `linked · coordinator online`.

With no relay, A still plays the whole story. A hospital that isn't connected gets a clearly labelled **SIMULATED** reply, and the badge reads `REHEARSAL`.

### Keys (page A)

| Key | Action |
| --- | --- |
| → / Space | next: standby → question → ask → route → approval |
| ← | back |
| A | ask the network |
| S | simulate a hospital that isn't answering |
| P | sign on screen (a signature pad) |
| E | enroll the surgeon's signature on file (the next signature becomes the reference) |
| R | reset everything, including B and C |
| F | fullscreen |
| H | help and relay address |

### Suggested run of show

1. **Standby.** Show the 28,000 headline and the stats. Press → to reveal the question.
2. Press → again to ask. Packets fly to both hospitals, and B and C each run their agent live. Harbor Point answers **yes · 1.0 h**. Riverbend answers **no**.
3. Press → to show the route map (Oakland → San Jose on I-880). It reads "Awaiting surgeon approval".
4. Press → for the approval slide. Before the demo, press **E** and sign once to enroll a reference. On stage, drop a phone photo of the signature, or press **P** and sign. The model's view appears, then the checks. **Approve & dispatch** unlocks only if the check passes.
5. Click **Approve & dispatch**. On B, the "Approved by the receiving surgeon" card appears. Click **Hand kidney to courier** (it goes automatically after 20 s). A switches to the map and the courier drives to San Jose.

## What crosses the wire

- **A → hospitals:** `organ, recipient_blood, destination, max_transport_h` and the question text. No name, chart, HLA or antibodies.
- **Hospitals → A:** `answer, organ, eta_h, reason`, plus progress stages. Page B/C enforces this with an allowlist in code. Any other field, a field with a sensitive name, or free text over 80 characters is blocked before sending.
- **A → Harbor Point on approval:** `decision, verified: signature_cv, signer_role`. The signature image never leaves A.
- The relay prints every message it carries, so you can show the terminal to prove it.

## The "RAG AI" on B and C

1. BM25 retrieval (k1 1.4, b 0.75) over the hospital's own records, in the browser.
2. Code checks each retrieved record: organ, ABO compatibility, status and cold-ischemia time. A cross-check over all records must agree.
3. An explanation for the hospital's own staff. If Ollama is running on that Mac, a local model writes it: `OLLAMA_ORIGINS="*" ollama serve`, and have a model pulled, e.g. `ollama pull qwen3.5:4b`. Otherwise a template writes it. The page says which one wrote it. **Code makes the decision either way.**
4. The answer is sent as a category only.

Each hospital's records live in `src/hospitals.json`. Edit them, then run `python3 build.py`.

## Computer-vision signature check (A)

Runs on the canvas, in the browser:

- Adaptive (Bradley) plus Otsu thresholding.
- 8-connected stroke components.
- Shape checks: ink found, aspect ratio, ink coverage, stroke count, stroke width.
- A shape match against the enrolled reference: correlation of a 40×12 density grid plus horizontal and vertical profiles, threshold 0.50.

This is a demo check, not forensic signature verification. The surgeon still clicks Approve.

## Editing

- Headline, stats, sources and the surgeon's name are at the top of the script in `src/coordinator.html`.
- The shared look is in `src/shared.css`; the message bus is in `src/bus.js`.
- Rebuild with `python3 build.py`. It writes the three self-contained files into `dist/`.

All patients, donors and hospitals are fictional. The data is synthetic.
