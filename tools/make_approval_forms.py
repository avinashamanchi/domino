"""Make synthetic surgeon-approval forms (PNG) for step 3 of the demo.

    uv run --python 3.11 --with pillow --with segno python tools/make_approval_forms.py

Writes approval-forms/*.png.  Each form carries a QR code with its fields and the position of the
signature box and decision boxes, so the projector can extract fields and check for ink on its own.
"""
import json
import sys
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flower"))
from domino_app.screening import candidate_token  # noqa: E402

OUT = ROOT / "approval-forms"
REQ = "REQ-2026-0929-A1"
W, H = 1700, 2200
NAVY, TEAL, INK, GREY = (14, 39, 64), (79, 163, 165), (20, 30, 70), (110, 120, 135)
FONTS = "/System/Library/Fonts/Supplemental/"


def font(name, size):
    for candidate in (FONTS + name, "/Library/Fonts/" + name):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size)


def make(filename, *, token, signed=True, approve=True):
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    bold, reg, small = font("Arial Bold.ttf", 44), font("Arial.ttf", 36), font("Arial.ttf", 28)

    d.rectangle([0, 0, W, 170], fill=NAVY)
    d.rectangle([0, 170, W, 182], fill=TEAL)
    d.text((80, 42), "ALDER MEDICAL CENTER", font=font("Arial Bold.ttf", 56), fill="white")
    d.text((80, 112), "Kidney Transplant Program  ·  Paired exchange approval  ·  AMC-KTP-04 §2.4", font=small, fill=(196, 228, 247))

    d.text((80, 240), "Exchange proposal: surgeon approval", font=font("Arial Bold.ttf", 52), fill=NAVY)
    d.text((80, 312), "SYNTHETIC DEMO FORM", font=small, fill=(200, 120, 20))

    recipient = candidate_token(REQ, "alder", "A1") + "-P"
    fields = [
        ("Form ID", "APF-2026-0929-01"),
        ("Request ID", REQ),
        ("Recipient (Alder)", "Maria Alvarez · pair A1"),
        ("Recipient token", recipient),
        ("Alder donor", "Elena Alvarez (sister) · blood B"),
        ("Partner program", "Harbor Point Hospital, Oakland"),
        ("Partner candidate", token),
        ("Exchange", "Elena → candidate's patient;  candidate's donor → Maria"),
        ("Proposed window", "Oct 12 – Oct 23, 2026"),
        ("Screening", "blood type OK · crossmatch negative both ways · ready"),
    ]
    y = 400
    for label, value in fields:
        d.text((80, y), label, font=small, fill=GREY)
        d.text((480, y - 4), value, font=reg, fill=INK)
        d.line([80, y + 52, 1620, y + 52], fill=(230, 230, 230), width=2)
        y += 70

    # Decision boxes
    d.text((80, 1150), "Decision", font=bold, fill=NAVY)
    chk_approve, chk_decline = [80, 1230, 140, 1290], [800, 1230, 860, 1290]
    for box, text in ((chk_approve, "Approve exchange for scheduling"), (chk_decline, "Do not approve")):
        d.rectangle(box, outline=NAVY, width=4)
        d.text((box[2] + 24, box[1] + 8), text, font=reg, fill=INK)
    mark = chk_approve if approve else chk_decline
    d.line([mark[0] + 10, mark[1] + 30, mark[0] + 26, mark[3] - 10], fill=INK, width=8)
    d.line([mark[0] + 26, mark[3] - 10, mark[2] - 6, mark[1] + 6], fill=INK, width=8)

    # Signature box
    sig = [80, 1440, 1100, 1680]
    d.text((80, 1380), "Transplant surgeon signature", font=small, fill=GREY)
    d.rectangle(sig, outline=(200, 205, 212), width=2)
    d.line([sig[0] + 30, sig[3] - 50, sig[2] - 30, sig[3] - 50], fill=(200, 205, 212), width=2)
    if signed:
        script = font("SnellRoundhand.ttc", 120)
        d.text((sig[0] + 70, sig[1] + 40), "M. Castillo", font=script, fill=INK)
        d.line([sig[0] + 90, sig[3] - 70, sig[0] + 620, sig[3] - 84], fill=INK, width=4)
    d.text((80, 1700), "Dr. M. Castillo, MD  ·  Transplant Surgery, Alder Medical Center", font=reg, fill=INK)
    d.text((80, 1752), "Date: 2026-09-29", font=reg, fill=INK)

    # QR with the form's fields and layout (form pixels)
    qr_x, qr_y, scale, border = 1260, 1200, 6, 4
    payload_base = {
        "form": "APF-2026-0929-01", "request_id": REQ, "candidate_token": token, "recipient_token": recipient,
        "partner": "Harbor Point Hospital", "surgeon": "Dr. M. Castillo", "date": "2026-09-29",
    }
    layout = {"sig": sig, "approve": chk_approve, "decline": chk_decline}
    for _ in range(2):  # symbol size depends on payload length; settle it
        payload = {**payload_base, "layout": {**layout, "qr": [qr_x + border * scale, qr_y + border * scale, 0]}}
        qr = segno.make(json.dumps(payload, separators=(",", ":")), error="m")
        symbol = qr.symbol_size(scale=scale, border=0)[0]
        payload["layout"]["qr"][2] = symbol
        qr = segno.make(json.dumps(payload, separators=(",", ":")), error="m")
        if qr.symbol_size(scale=scale, border=0)[0] == symbol:
            break
    tmp = OUT / "_qr.png"
    qr.save(tmp, scale=scale, border=border)
    qimg = Image.open(tmp).convert("RGB")
    tmp.unlink()
    qr_x = W - 80 - qimg.width
    payload["layout"]["qr"][:2] = [qr_x + border * scale, qr_y + border * scale]
    qr = segno.make(json.dumps(payload, separators=(",", ":")), error="m")
    qr.save(tmp, scale=scale, border=border)
    qimg = Image.open(tmp).convert("RGB")
    tmp.unlink()
    img.paste(qimg, (qr_x, qr_y))

    d.rectangle([0, H - 110, W, H], fill=NAVY)
    d.text((80, H - 76), "Synthetic data. All patients, donors and hospitals are fictional.", font=small, fill="white")
    img.save(OUT / filename)
    print(OUT / filename, payload["layout"])


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    good = candidate_token(REQ, "harbor", "H1")
    make("approval-signed.png", token=good)
    make("approval-unsigned.png", token=good, signed=False)
    make("approval-wrong-candidate.png", token="HP-000000")
