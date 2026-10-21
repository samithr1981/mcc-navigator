"""Knowledge base: the MCC master list, travel and lodging name lists, and facts derived from them.

Everything in `data/mcc_master.json` and `data/te_merchants.csv` is extracted from the Merchant Data
Standards Manual by `kb_build/build_kb.py`. The groupings (`family`) and the special-handling tags are the
Navigator's own, built from the manual's rules (page references are kept in `rules.py`).
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# Navigator's own grouping of the MCC list, by code range. Not part of the manual.
FAMILIES = [
    (742, 780, "Agriculture and animal services"), (1520, 1799, "Contractors"), (2741, 2842, "Printing and publishing"),
    (3000, 3299, "Airlines (named)"), (3300, 3350, "Airlines (named)"), (3351, 3441, "Car rental (named)"),
    (3500, 3999, "Lodging (named)"), (4011, 4789, "Transportation"), (4812, 4899, "Telecom and media"),
    (4900, 4900, "Utilities"), (5013, 5199, "Wholesale and business supplies"), (5200, 5399, "Home improvement and general merchandise"),
    (5411, 5499, "Food stores"), (5511, 5599, "Vehicle dealers and fuel"), (5611, 5699, "Apparel"),
    (5712, 5735, "Home furnishings and electronics"), (5811, 5814, "Eating and drinking"), (5815, 5818, "Digital goods"),
    (5912, 5999, "Specialty retail"), (6010, 6540, "Financial and quasi-cash"), (7011, 7033, "Lodging and camps"),
    (7210, 7299, "Personal services"), (7311, 7399, "Business services"), (7512, 7549, "Vehicle rental and services"),
    (7622, 7699, "Repair services"), (7800, 7802, "Government lotteries and gaming (US)"), (7829, 7999, "Entertainment and recreation"),
    (8011, 8099, "Health"), (8111, 8111, "Legal"), (8211, 8299, "Education"), (8351, 8351, "Child care"),
    (8398, 8699, "Membership and charitable organizations"), (8734, 8999, "Professional services"),
    (9211, 9950, "Government and other"),
]
DIRECT_MARKETING = {"5960", "5962", "5963", "5964", "5965", "5966", "5967", "5968", "5969"}


def family_of(code: str) -> str:
    n = int(code)
    if code in DIRECT_MARKETING:
        return "Direct marketing"
    for lo, hi, name in FAMILIES:
        if lo <= n <= hi:
            return name
    return "Other"


@dataclass(frozen=True)
class MCC:
    code: str
    title: str
    description: str
    included: tuple[str, ...]
    similar: tuple[tuple[str, str], ...]
    page: int
    family: str
    tags: frozenset = field(default_factory=frozenset)
    regions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.code} – {self.short_title}"

    @property
    def short_title(self) -> str:
        t = re.sub(r"\s+", " ", self.title).strip()
        return t if len(t) <= 80 else t[:77].rstrip(" ,") + "…"


def _tags_and_regions(code: str, title: str, desc: str) -> tuple[set, list, list]:
    blob = f"{title} {desc}".lower()
    tags, regions, notes = set(), [], []
    if "us region only" in blob or "(us region only)" in blob.replace("u.s.", "us"):
        regions.append("US only")
    if re.search(r"germany only", blob):
        regions.append("Germany only")
    if "non-u.s. region" in blob:
        regions.append("Outside US")
    if code == "9405":
        regions.append("US only")
    if "visa use only" in blob:
        tags.add("network_use_only")
        notes.append("Reserved for network use. Acquirers do not assign this MCC to merchants.")
    if "government only" in blob:
        tags.add("government_only")
    if "business-to-business" in blob:
        tags.add("b2b")
    if code in DIRECT_MARKETING:
        tags.add("direct_marketing")
    if code == "5300":
        tags.add("wholesale_club")
    if code in {"4511", "7512", "7011"}:
        tags.add("te_generic")
    if code in {"5122", "5912", "5962", "5966", "5967", "5993", "7273", "7995"}:
        tags.add("high_brand_risk_card_absent")
    if code in {"4816", "5816", "6051"}:
        tags.add("high_brand_risk_conditional")
    if code in {"6010", "6011", "6012", "6051", "4829", "6540"}:
        tags.add("cash_and_quasi_cash")
    if code in {"7995", "7800", "7801", "7802", "9406"}:
        tags.add("gambling")
    if code == "5542":
        tags.add("afd")
    if code == "5262":
        tags.add("marketplace")
    if code.endswith("99") and ("not elsewhere classified" in blob or "miscellaneous" in blob):
        tags.add("catch_all")
    if "not elsewhere classified" in title.lower():
        tags.add("catch_all")
    return tags, regions, notes


@lru_cache(maxsize=1)
def load(master_path: str | None = None) -> dict[str, MCC]:
    path = Path(master_path) if master_path else DATA / "mcc_master.json"
    raw = json.loads(path.read_text())
    out = {}
    for r in raw:
        code = r["mcc"]
        title = re.sub(r"\s+\.+\s*$", "", r["title"]).replace(" )", ")").strip()
        tags, regions, notes = _tags_and_regions(code, title, r["description"])
        out[code] = MCC(
            code=code, title=title, description=r["description"], included=tuple(r["included"]),
            similar=tuple((s["mcc"], s["title"]) for s in r["similar"] if s["mcc"]), page=int(r["page"]),
            family=family_of(code), tags=frozenset(tags), regions=tuple(regions), notes=tuple(notes),
        )
    return out


def get(code: str) -> MCC | None:
    return load().get(str(code).zfill(4))


# --------------------------------------------------------------------------- named travel and lodging
@dataclass(frozen=True)
class NamedMCC:
    code: str
    merchant: str
    required_name: str
    kind: str  # airline, car_rental, lodging
    page: int


def _kind(code: str) -> str:
    n = int(code)
    if 3000 <= n <= 3350:
        return "airline"
    if 3351 <= n <= 3500:
        return "car_rental"
    return "lodging"


@lru_cache(maxsize=1)
def named_merchants() -> list[NamedMCC]:
    rows = []
    with open(DATA / "te_merchants.csv", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(NamedMCC(r["mcc"], r["merchant"], r["required_name"], _kind(r["mcc"]), int(r["page"] or 0)))
    return rows


_STOP = {"hotel", "hotels", "inn", "inns", "resort", "resorts", "and", "the", "of", "air", "airlines", "airways", "international",
         "rent", "a", "car", "casino", "suites", "lodge", "motel", "motels", "by", "de", "du", "las", "los"}


def _norm_name(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", s.lower())
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _tokens(s: str) -> set[str]:
    return {t for t in _norm_name(s).split() if t not in _STOP and len(t) > 1}


def match_named(name: str, kind: str | None = None) -> list[tuple[NamedMCC, float]]:
    """Find named airline, car rental or lodging MCCs that match a merchant or brand name. Returns (entry, score)."""
    q = _norm_name(name)
    qt = _tokens(name)
    out = []
    if not q:
        return out
    for e in named_merchants():
        if kind and e.kind != kind:
            continue
        en = _norm_name(e.merchant)
        et = _tokens(e.merchant)
        if not et:
            continue
        if q == en or q == _norm_name(e.required_name):
            score = 1.0
        elif en and (f" {en} " in f" {q} " or f" {q} " in f" {en} ") and len(en) >= 4:
            score = 0.92
        elif qt and et:
            inter = len(qt & et)
            score = 0.85 * inter / max(len(et), len(qt)) if inter and inter == min(len(et), len(qt)) and len(et) > 1 else 0.0
            if inter and len(et) == 1 and et <= qt:
                score = 0.8
        else:
            score = 0.0
        if score >= 0.75:
            out.append((e, score))
    out.sort(key=lambda t: -t[1])
    return out[:5]
