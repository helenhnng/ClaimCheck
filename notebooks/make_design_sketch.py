"""Draws docs/design_sketch.jpg (the design sketch of ClaimCheck).

Run: .venv/bin/python notebooks/make_design_sketch.py
Needs Pillow (installed with Streamlit) and the Arial font that ships with macOS.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from claimcheck import paths

W, H = 2600, 1700
INK, MUTED, LINE = "#1F2933", "#52606D", "#7B8794"
PANEL, PANEL_EDGE = "#F5F7FA", "#CBD2D9"
ACCENT = "#0B5F6B"
FONT_DIR = Path("/System/Library/Fonts/Supplemental")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / ("Arial Bold.ttf" if bold else "Arial.ttf")), size)


img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)


def wrap(text: str, fnt, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if d.textlength(trial, font=fnt) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    return lines + [current]


def box(x, y, w, h, title, body="", fill=PANEL, edge=PANEL_EDGE, title_fill=INK, body_fill=MUTED,
        title_size=30, body_size=24, center=False):
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=fill, outline=edge, width=3)
    tf, bf = font(title_size, bold=True), font(body_size)
    pad = 22
    title_lines = wrap(title, tf, w - 2 * pad)
    body_lines = wrap(body, bf, w - 2 * pad) if body else []
    title_h, body_h = title_size + 8, body_size + 8
    total = len(title_lines) * title_h + (10 if body_lines else 0) + len(body_lines) * body_h
    cy = y + (h - total) / 2 if center or not body_lines else y + pad
    for line in title_lines:
        tx = x + (w - d.textlength(line, font=tf)) / 2 if center else x + pad
        d.text((tx, cy), line, font=tf, fill=title_fill)
        cy += title_h
    cy += 10
    for line in body_lines:
        tx = x + (w - d.textlength(line, font=bf)) / 2 if center else x + pad
        d.text((tx, cy), line, font=bf, fill=body_fill)
        cy += body_h


def arrow(points, color=LINE, width=4, dashed=False, head=True):
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if dashed:
            length = max(abs(x2 - x1), abs(y2 - y1))
            steps = max(int(length // 24), 1)
            for i in range(steps):
                a, b = i / steps, (i + 0.55) / steps
                d.line([(x1 + (x2 - x1) * a, y1 + (y2 - y1) * a), (x1 + (x2 - x1) * b, y1 + (y2 - y1) * b)],
                       fill=color, width=width)
        else:
            d.line([(x1, y1), (x2, y2)], fill=color, width=width)
    if head:
        (x1, y1), (x2, y2) = points[-2], points[-1]
        s = 14
        if x2 > x1:
            tri = [(x2, y2), (x2 - s * 1.6, y2 - s), (x2 - s * 1.6, y2 + s)]
        elif x2 < x1:
            tri = [(x2, y2), (x2 + s * 1.6, y2 - s), (x2 + s * 1.6, y2 + s)]
        elif y2 > y1:
            tri = [(x2, y2), (x2 - s, y2 - s * 1.6), (x2 + s, y2 - s * 1.6)]
        else:
            tri = [(x2, y2), (x2 - s, y2 + s * 1.6), (x2 + s, y2 + s * 1.6)]
        d.polygon(tri, fill=color)


def label(x, y, text, size=23, fill=MUTED, bold=False, anchor="la"):
    d.text((x, y), text, font=font(size, bold), fill=fill, anchor=anchor)


def section(y, number, text):
    d.ellipse([80, y, 128, y + 48], fill=ACCENT)
    d.text((104, y + 24), str(number), font=font(28, True), fill="white", anchor="mm")
    d.text((146, y + 24), text, font=font(34, True), fill=INK, anchor="lm")


# --- title ---------------------------------------------------------------------
d.text((80, 50), "ClaimCheck: design sketch", font=font(58, True), fill=INK)
d.text((80, 126), "Checks a home-care claim before it is sent: paid or denied, which code, which rule, how to fix it. "
                  "The biller decides.", font=font(27), fill=MUTED)

# --- 1. where it sits ----------------------------------------------------------
section(196, 1, "Where it sits in Exchange4Health")
BW, BH, GAP, FY = 310, 120, 116, 300
steps = ["Caregiver clocks in / out", "EVV visit record", "Claim drafted", "ClaimCheck", "Payer",
         "Outcome: paid / denied"]
xs = [80 + i * (BW + GAP) for i in range(len(steps))]
for i, (x, text) in enumerate(zip(xs, steps)):
    if text == "ClaimCheck":
        box(x, FY, BW, BH, text, fill=ACCENT, edge=ACCENT, title_fill="white", title_size=36, center=True)
    else:
        box(x, FY, BW, BH, text, center=True)
    if i:
        arrow([(xs[i - 1] + BW + 6, FY + BH / 2), (x - 6, FY + BH / 2)])
label(xs[3] + BW + GAP / 2, FY + BH / 2 - 36, "submit", anchor="ma")

# decided claims become history (dashed, over the top)
cc_x, out_x = xs[3] + BW / 2, xs[5] + BW / 2
arrow([(out_x, FY - 6), (out_x, FY - 44), (cc_x, FY - 44), (cc_x, FY - 6)], dashed=True)
label((cc_x + out_x) / 2, FY - 78, "decided claims become history for later checks", anchor="ma")

# biller loop
BY = 480
box(xs[3], BY, BW, 96, "Biller", "decides every claim", center=True)
arrow([(cc_x, FY + BH + 6), (cc_x, BY - 6)])
label(cc_x + 18, FY + BH + 18, "fix / hold / review")
draft_x = xs[2] + BW / 2
arrow([(xs[3] - 6, BY + 48), (draft_x, BY + 48), (draft_x, FY + BH + 6)])
label(draft_x + 18, BY + 58, "corrects the claim")

# --- 2. inside ClaimCheck ------------------------------------------------------
section(640, 2, "Inside ClaimCheck")

# rule settings + payer documents
SX, SY, SW, SH = 1240, 640, 460, 96
box(SX, SY, SW, SH, "Rule settings file", "dated numbers for each payer", fill="#E6F4F1", edge=ACCENT, center=True)
DX, DW = 1960, 560
box(DX, SY, DW, SH, "Payer manuals + bulletins", "5 documents, 3 payers", center=True)
arrow([(DX - 6, SY + SH / 2), (SX + SW + 6, SY + SH / 2)], dashed=True)
label((SX + SW + DX) / 2, SY + SH + 8, "read once with AI,", anchor="ma")
label((SX + SW + DX) / 2, SY + SH + 36, "then reviewed by a person", anchor="ma")

# inputs
IX, IW, IH, IGAP, IY = 80, 420, 82, 18, 790
inputs = [("Claims file", "uploaded CSV"), ("EVV visits", "on file"), ("Authorizations", "on file"),
          ("Past decided claims", "on file")]
for i, (title, sub) in enumerate(inputs):
    y = IY + i * (IH + IGAP)
    d.rounded_rectangle([IX, y, IX + IW, y + IH], radius=12, fill="white", outline=PANEL_EDGE, width=3)
    d.text((IX + 22, y + IH / 2), title, font=font(27, True), fill=INK, anchor="lm")
    d.text((IX + IW - 22, y + IH / 2), sub, font=font(23), fill=MUTED, anchor="rm")
inputs_bottom = IY + 4 * IH + 3 * IGAP
mid_y = (IY + inputs_bottom) / 2

# pipeline
PX, PW, PGAP, PH = 600, 320, 56, 250
PY = int(mid_y - PH / 2)
stages = [
    ("1  Clean", "Makes payer names, codes and dates consistent. Refuses what it cannot read."),
    ("2  Timeline", "Walks claims in submission order: already billed, units left, paid units per day."),
    ("3  Rules", "Ten checks, D01 to D10. Each returns the rule, its source and a fix."),
    ("4  Code order", "Several rules broken? Picks the one code the payer reports."),
    ("5  Review routing", "Decides what a person must look at."),
]
pxs = [PX + i * (PW + PGAP) for i in range(len(stages))]
for i, (x, (title, body)) in enumerate(zip(pxs, stages)):
    box(x, PY, PW, PH, title, body, fill="white", edge=ACCENT, title_fill=ACCENT, title_size=31, body_size=24)
    if i:
        arrow([(pxs[i - 1] + PW + 6, PY + PH / 2), (x - 6, PY + PH / 2)], color=ACCENT)
arrow([(IX + IW + 8, mid_y), (PX - 6, mid_y)], color=ACCENT)
d.line([(IX + IW + 8, IY + 10), (IX + IW + 8, inputs_bottom - 10)], fill=ACCENT, width=4)

rules_x = pxs[2] + PW / 2
arrow([(rules_x, SY + SH + 6), (rules_x, PY - 6)], color=ACCENT)

# outcomes
bus_y, CY, CW, CH, CGAP = PY + PH + 60, PY + PH + 110, 440, 130, 30
chips = [
    ("Submit", "360", "no rule broken", "#E3F4E8", "#2E7D4F"),
    ("Fix, then submit", "147", "rule broken, fix given", "#FBE9E7", "#B93A2B"),
    ("Hold", "4", "visit awaiting verification", "#FFF4D6", "#A66B00"),
    ("Needs a person", "35", "inferred rule, corrected claim, near a limit", "#E6F0FA", "#2F6DAA"),
]
cxs = [PX + i * (CW + CGAP) for i in range(len(chips))]
last_x = pxs[4] + PW / 2
d.line([(last_x, PY + PH + 6), (last_x, bus_y)], fill=LINE, width=4)
d.line([(cxs[0] + CW / 2, bus_y), (max(last_x, cxs[-1] + CW / 2), bus_y)], fill=LINE, width=4)
for x, (title, count, sub, fill, edge) in zip(cxs, chips):
    arrow([(x + CW / 2, bus_y), (x + CW / 2, CY - 6)])
    d.rounded_rectangle([x, CY, x + CW, CY + CH], radius=14, fill=fill, outline=edge, width=3)
    d.text((x + 22, CY + 42), title, font=font(30, True), fill=INK, anchor="lm")
    d.text((x + CW - 22, CY + 42), count, font=font(40, True), fill=edge, anchor="rm")
    d.text((x + 22, CY + 96), sub, font=font(21), fill=MUTED, anchor="lm")
label(IX, CY + 22, "Recommended action", size=28, fill=INK, bold=True)
label(IX, CY + 64, "for the 546 claims to check")

# --- 3. facts ------------------------------------------------------------------
FY2 = CY + CH + 70
section(FY2, 3, "What to know")
facts = [
    ("No AI model is called per claim",
     "AI read the payer documents and wrote the code. Each decision is plain code: exact, repeatable, explainable."),
    ("Held-back test: 98.4% paid / denied accuracy",
     "1,149 past claims, scored once. 0 false alarms. 94.5% of denials caught."),
    ("Never predicted: D99 (about 2% of claims)",
     "'Contact payer' denials. Nothing in the data predicts them: two learned models scored at chance."),
]
FW, FGAP, FH = 790, 35, 170
for i, (title, body) in enumerate(facts):
    box(80 + i * (FW + FGAP), FY2 + 70, FW, FH, title, body, title_size=28, body_size=23)

out = paths.DOCS_DIR / "design_sketch.jpg"
img.save(out, "JPEG", quality=93, dpi=(200, 200))
print(f"wrote {out} {img.size}, bottom of content at y={FY2 + 70 + FH}")
