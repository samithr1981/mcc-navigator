"""Build the MCC knowledge base from a Merchant Data Standards Manual PDF.

Usage:  python kb_build/build_kb.py path/to/manual.pdf

Reads the MCC listing (section 2) and writes data/mcc_master.json and data/te_merchants.csv.
It depends on the manual's page layout (four columns: code, title and description, included, similar
merchants). If the layout of a new edition changes, check the printed summary and the sample output.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pdfplumber

COL_DESC, COL_INC, COL_SIM = 84.0, 288.0, 400.0   # left edges in points
TOP_SKIP, BOTTOM_SKIP = 95.0, 735.0
DROP_LINES = {"Airlines and Air Carriers", "Car Rental Agencies", "Lodging – Hotels, Motels, Resorts"}
SIM_START = re.compile(r"^\d{4}\s*[–\-—]")


def lines_of(words, tol=2.5):
    """Group words into lines by vertical position. Returns [(top, x0, text)]."""
    out = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if out and abs(out[-1][0] - w["top"]) <= tol:
            out[-1][2].append(w)
        else:
            out.append([w["top"], w["x0"], [w]])
    return [(t, ws[0]["x0"], " ".join(x["text"] for x in sorted(ws, key=lambda x: x["x0"]))) for t, _, ws in out]


def build(pdf_path: str):
    pdf = pdfplumber.open(pdf_path)
    entries, order = {}, []
    te_rows, te_group = [], None
    current = None
    in_listing = False
    for pno, page in enumerate(pdf.pages, start=1):
        text = page.extract_text() or ""
        if "Section 2: Merchant Category Code Listing" not in text.split("\n")[0:2].__str__() and not in_listing:
            continue
        if "Section 3: New MCC" in text:
            break
        in_listing = True
        words = [w for w in page.extract_words() if BOTTOM_SKIP > w["top"] > TOP_SKIP or (w["top"] <= TOP_SKIP and False)]
        # table header words sit above TOP_SKIP; footer below BOTTOM_SKIP
        rects = [r for r in page.rects if r["width"] > 300 and (r.get("non_stroking_color") not in (None, (1, 1, 1), [1, 1, 1], 1, (1,), [1]))]
        anchors = [w for w in words if w["x0"] < 80 and re.fullmatch(r"\d{4}", w["text"])]
        # T&E rows (airline, car rental, lodging names) are not MCC definitions
        te_anchor = [w for w in anchors if 3000 <= int(w["text"]) <= 3999]
        reg_anchor = [w for w in anchors if w not in te_anchor]
        te_sorted = sorted(te_anchor, key=lambda w: w["top"])
        for i, w in enumerate(te_sorted):
            lo = (te_sorted[i - 1]["top"] + w["top"]) / 2 if i else w["top"] - 14
            hi = (w["top"] + te_sorted[i + 1]["top"]) / 2 if i + 1 < len(te_sorted) else w["top"] + 14
            row = sorted([x for x in words if lo <= x["top"] < hi and x["x0"] > 80], key=lambda x: (round(x["top"] / 3), x["x0"]))
            name = " ".join(x["text"] for x in row if x["x0"] < COL_INC)
            req = " ".join(x["text"] for x in row if x["x0"] >= COL_INC)
            te_rows.append({"mcc": w["text"], "merchant": name, "required_name": req, "page": pno - 4})
        reg_tops = {round(w["top"]) for w in reg_anchor}
        bands = []
        for a in sorted(reg_anchor, key=lambda w: w["top"]):
            band = next((r for r in rects if r["top"] - 3 <= a["top"] <= r["bottom"] + 1), None)
            bottom = band["bottom"] if band else a["top"] + 6
            title_words = [x for x in words if a["top"] - 4 <= x["top"] <= bottom - 2 and x["x0"] > 80]
            title = " ".join(x["text"] for x in sorted(title_words, key=lambda x: (round(x["top"] / 3), x["x0"])))
            bands.append((a["top"], bottom, a["text"], title))
        used_title_ids = set()
        # assign each non-anchor, non-title word to the entry whose block contains it
        starts = [b[0] for b in bands]
        def entry_for(top):
            cur = current
            for b in bands:
                if top >= b[0] - 3:
                    cur = b[2]
            return cur
        for top0, bottom, code, title in bands:
            if code not in entries:
                entries[code] = {"mcc": code, "title": title, "page": pno - 4, "desc": [], "inc": [], "sim": []}
                order.append(code)
        # the named airline, car rental and lodging tables are read separately above, so skip them here
        zone = None
        if te_anchor:
            head = [l[0] for l in lines_of([x for x in words if x["x0"] > 80 and x["x0"] < COL_INC]) if l[2] in DROP_LINES]
            z0 = min(head) - 3 if head else TOP_SKIP
            nxt = [b[0] for b in bands if b[0] > min(w["top"] for w in te_anchor)]
            zone = (z0, min(nxt) - 4 if nxt else 1e9)
        buckets = {}
        for w in words:
            if w in anchors:
                continue
            if zone and zone[0] <= w["top"] < zone[1]:
                continue
            in_band = next((b for b in bands if b[0] - 4 <= w["top"] <= b[1] - 2), None)
            if in_band and w["x0"] > 80:
                continue  # title text
            if w["x0"] < 80:
                continue
            code = entry_for(w["top"])
            if code is None:
                continue
            col = "desc" if w["x0"] < COL_INC else ("inc" if w["x0"] < COL_SIM else "sim")
            buckets.setdefault((code, col), []).append(w)
        # T&E zone: words after a T&E anchor line belong to nothing
        te_tops = [w["top"] for w in te_anchor]
        for (code, col), ws in buckets.items():
            if te_tops:
                ws = [w for w in ws if not (min(te_tops) - 3 <= w["top"])] if code == (current or code) and not bands else ws
            ls = lines_of(ws)
            ls = [l for l in ls if l[2] not in DROP_LINES and not l[2].startswith("MCC Merchant Name") and not l[2].startswith("Merchant Name")]
            if col == "desc":
                entries[code]["desc"].append(" ".join(l[2] for l in ls))
            elif col == "inc":
                left = min((l[1] for l in ls), default=0)
                items = []
                for _, x0, txt in ls:
                    if items and x0 > left + 3.5:
                        items[-1] += " " + txt
                    else:
                        items.append(txt)
                entries[code]["inc"].extend(items)
            else:
                items = []
                for _, x0, txt in ls:
                    if SIM_START.match(txt) or not items:
                        items.append(txt)
                    else:
                        items[-1] += " " + txt
                entries[code]["sim"].extend(items)
        if bands:
            current = bands[-1][2]
    return entries, order, te_rows


def clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"(?<=[A-Za-z])- (?=[a-z])", "-", s)  # "card- present" -> "card-present"


def main(pdf_path: str):
    entries, order, te_rows = build(pdf_path)
    out = []
    for code in order:
        e = entries[code]
        sims = []
        for s in e["sim"]:
            m = re.match(r"^(\d{4})\s*[–\-—]+\s*(.*)$", clean(s))
            sims.append({"mcc": m.group(1), "title": m.group(2)} if m else {"mcc": "", "title": clean(s)})
        out.append({"mcc": code, "title": clean(e["title"]), "description": clean(" ".join(e["desc"])),
                    "included": [clean(x) for x in e["inc"] if clean(x)], "similar": sims, "page": e["page"]})
    root = Path(__file__).resolve().parent.parent / "data"
    root.mkdir(exist_ok=True)
    (root / "mcc_master.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    with open(root / "te_merchants.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["mcc", "merchant", "required_name", "page"])
        w.writeheader()
        for r in te_rows:
            r = {k: clean(str(v)) for k, v in r.items()}
            r["merchant"] = re.sub(r"^(Merchant Name|Required Name in Authorization Request/Clearing Record)\s*", "", r["merchant"])
            r["required_name"] = re.sub(r"^Required Name in Authorization Request/Clearing Record\s*", "", r["required_name"])
            w.writerow(r)
    print(f"{len(out)} MCC definitions, {len(te_rows)} named travel and lodging MCCs -> {root}")


if __name__ == "__main__":
    main(sys.argv[1])
