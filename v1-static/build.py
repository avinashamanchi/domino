"""Build the three standalone demo pages into dist/ (fonts, styles and scripts inlined, no network needed).

    python3 build.py
"""
import base64
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC, DIST, FONTS = (os.path.join(HERE, d) for d in ("src", "dist", "fonts"))

FACES = [
    ("Ubuntu", 400, "normal", "ubuntu-latin-400-normal.woff2"),
    ("Ubuntu", 400, "italic", "ubuntu-latin-400-italic.woff2"),
    ("Ubuntu", 500, "normal", "ubuntu-latin-500-normal.woff2"),
    ("Ubuntu", 700, "normal", "ubuntu-latin-700-normal.woff2"),
    ("Ubuntu Condensed", 400, "normal", "ubuntu-condensed-latin-400-normal.woff2"),
    ("Ubuntu Mono", 400, "normal", "ubuntu-mono-latin-400-normal.woff2"),
]


def read(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return f.read()


def font_css():
    out = []
    for family, weight, style, file in FACES:
        with open(os.path.join(FONTS, file), "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        out.append(
            f"@font-face{{font-family:'{family}';font-style:{style};font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    return "\n".join(out)


def fill(template, **parts):
    for key, value in parts.items():
        marker = f"/*@{key}@*/"
        assert marker in template, marker
        template = template.replace(marker, value)
    return template


def main():
    os.makedirs(DIST, exist_ok=True)
    common = {"FONTS": font_css(), "SHARED": read("shared.css"), "BUS": read("bus.js")}
    hospitals = json.loads(read("hospitals.json"))
    demo_ask = hospitals.pop("demoAsk")

    pages = {"A-coordinator-alder.html": fill(read("coordinator.html"), **common)}
    for h in hospitals.values():
        config = {**h, "demoAsk": demo_ask}
        html = fill(read("hospital.html"), **common, CONFIG=json.dumps(config))
        pages[h["file"]] = html.replace("@TITLE@", f"{h['short']} · Domino")

    for name, html in pages.items():
        with open(os.path.join(DIST, name), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"dist/{name}  {len(html) // 1024} KB")


if __name__ == "__main__":
    main()
