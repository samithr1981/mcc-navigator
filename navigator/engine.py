"""Assessment engine: from a merchant profile to a ranked MCC recommendation with reasons, probes and findings."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from pathlib import Path

from . import kb, rules
from .disambig import applicable, Probe
from .textmatch import Index

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "network.json"


@lru_cache(maxsize=1)
def config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


@lru_cache(maxsize=1)
def index() -> Index:
    return Index()


CHANNELS = ["Card-present (shop, counter)", "Card-absent: website or app", "Card-absent: phone or mail order", "Both card-present and online"]


@dataclass
class SalesLine:
    text: str
    pct: float = 100.0


@dataclass
class Profile:
    legal_name: str = ""
    dba_name: str = ""
    country: str = "India"
    description: str = ""
    sales: list = field(default_factory=list)           # list[SalesLine]
    channel: str = CHANNELS[0]
    is_government: bool = False
    b2b_share: float = 0.0
    sells_digital_goods: bool = False
    is_marketplace_or_pf: bool = False
    perishables_pct: float | None = None
    annual_txn: int | None = None
    pay_at_pump: bool = False
    cash_or_quasi_cash: bool = False
    gambling: bool = False
    current_mcc: str = ""
    probe_answers: dict = field(default_factory=dict)    # probe id -> chosen option label


@dataclass
class Candidate:
    code: str
    title: str
    score: float
    entry_score: float
    desc_score: float
    matched_on: str
    matched_phrase: str
    reasons: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    page: int = 0


@dataclass
class Finding:
    level: str      # block, warn, info, ok
    title: str
    detail: str
    ref: str = ""


@dataclass
class Assessment:
    profile: Profile
    candidates: list
    confidence: str
    confidence_note: str
    probes: list
    findings: list
    secondary: list         # lines whose best MCC differs from the primary
    named: list
    primary: str = ""


def _primary_text(p: Profile) -> str:
    return (p.description + " " + " ".join(s.text for s in sorted(p.sales, key=lambda s: -s.pct)[:1])).strip()


def _is_us(country: str) -> bool:
    return country.strip().lower() in {"us", "usa", "united states", "united states of america", "u.s."}


def _adjust(m, p: Profile, mcc: kb.MCC):
    """Structural signals: multipliers applied to the text score. Returns (factor, reasons, flags)."""
    f, reasons, flags = 1.0, [], []
    tags = mcc.tags
    cfg = config()
    if mcc.code == "9702" or "network_use_only" in tags:
        return 0.0, [], ["Network use only: cannot be assigned to a merchant"]
    if mcc.code in cfg.get("extra_restricted_mccs", []):
        return 0.0, [], ["Restricted by this network's configuration"]
    if "government_only" in tags and not p.is_government:
        f *= 0.35; flags.append("Government entities only")
    if "government_only" in tags and p.is_government:
        f *= 1.15; reasons.append("Merchant is a government entity")
    for r in mcc.regions:
        if r == "US only" and not _is_us(p.country):
            f *= 0.1; flags.append("US region only")
        if r == "Germany only" and p.country.strip().lower() != "germany":
            f *= 0.1; flags.append("Germany only")
        if r == "Outside US" and _is_us(p.country):
            f *= 0.1; flags.append("Outside the US only")
    if "direct_marketing" in tags:
        if p.channel == CHANNELS[2]:
            f *= 1.1; reasons.append("Sells by phone or mail")
        else:
            f *= 0.75
    if "te_generic" not in tags and mcc.code.isdigit() and 3000 <= int(mcc.code) <= 3999:
        f *= 0.5  # named brand rows only via the named list
    if "b2b" in tags:
        if p.b2b_share >= 50:
            f *= 1.12; reasons.append(f"{p.b2b_share:.0f}% of sales are to businesses")
        elif p.b2b_share == 0:
            f *= 0.9
    if "catch_all" in tags:
        f *= 0.88
    if mcc.code == "5542" and not p.pay_at_pump:
        f *= 0.6
    if mcc.code == "5542" and p.pay_at_pump:
        f *= 1.25; reasons.append("Pay-at-pump (automated fuel) is a separate MCC")
    if mcc.code in {"5817", "5815", "5816", "5818"} and p.sells_digital_goods:
        f *= 1.15; reasons.append("Sells digital goods")
    if mcc.code in {"5817", "5815", "5818"} and not p.sells_digital_goods:
        f *= 0.7
    if "gambling" in tags and p.gambling:
        f *= 1.2; reasons.append("Takes wagers")
    if "cash_and_quasi_cash" in tags and p.cash_or_quasi_cash:
        f *= 1.15; reasons.append("Provides cash or quasi-cash")
    if mcc.code == "5262":
        f *= 1.3 if p.is_marketplace_or_pf else 0.6
    if "high_brand_risk_card_absent" in tags and p.channel != CHANNELS[0]:
        flags.append("High-brand-risk MCC when card-absent")
    if "high_brand_risk_conditional" in tags:
        flags.append("High-brand-risk in certain circumstances")
    return f, reasons, flags


def rank_text(text: str, p: Profile, top: int = 8) -> list[Candidate]:
    ix = index()
    raw = ix.rank(text, top=40)
    out = []
    for m in raw:
        mcc = kb.get(m.code)
        f, reasons, flags = _adjust(m, p, mcc)
        if f <= 0:
            continue
        s = min(1.0, m.score * f)
        out.append(Candidate(m.code, mcc.short_title, s, m.entry_score, m.desc_score, m.best_entry, m.best_phrase, reasons, flags, mcc.page))
    out.sort(key=lambda c: -c.score)
    return out[:top]


def named_matches(p: Profile) -> list:
    res = []
    for nm in {p.dba_name, p.legal_name}:
        if nm:
            for e, s in kb.match_named(nm):
                res.append((e, s))
    seen, out = set(), []
    for e, s in sorted(res, key=lambda x: -x[1]):
        if (e.code, e.merchant) not in seen:
            seen.add((e.code, e.merchant)); out.append((e, s))
    return out[:5]


def _confidence(c: list[Candidate], answered: bool) -> tuple[str, str]:
    if not c:
        return "None", "No MCC matched. Describe the business in more detail."
    top = c[0].score
    gap = top - (c[1].score if len(c) > 1 else 0)
    if top >= 0.62 and gap >= 0.10:
        lvl = "High"
    elif top >= 0.45 and gap >= 0.04:
        lvl = "Medium"
    else:
        lvl = "Low"
    note = (f"Match strength {top:.2f}; gap to second {gap:.2f}. These are text-match strengths, not probabilities. "
            "They show how closely the description fits the MCC definition, so a person should still read the definition.")
    if answered:
        note = "Answers to the probe questions were applied. " + note
    return lvl, note


def apply_probes(c: list[Candidate], probes: list[Probe], answers: dict) -> list[Candidate]:
    c = list(c)
    for pr in probes:
        ans = answers.get(pr.id)
        if not ans:
            continue
        pick = next((code for lab, code in pr.options if lab == ans), "")
        if not pick:
            continue
        mcc = kb.get(pick)
        hit = next((x for x in c if x.code == pick), None)
        if hit is None:
            hit = Candidate(pick, mcc.short_title, 0.0, 0.0, 0.0, "", "", page=mcc.page)
            c.append(hit)
        hit.score = max(hit.score, c[0].score) + 0.2
        hit.reasons.append(f"Answer to '{pr.title}': {ans}")
    c.sort(key=lambda x: -x.score)
    return c


def assess(p: Profile, top: int = 8) -> Assessment:
    sales = [s for s in p.sales if s.text.strip()]
    primary_text = _primary_text(p) or p.description
    cands = rank_text(primary_text, p, top=top + 4)
    # named travel / lodging
    named = named_matches(p)
    for e, s in named:
        mcc = kb.get(e.code)
        if mcc and not any(x.code == e.code for x in cands):
            cands.insert(0, Candidate(e.code, mcc.short_title, 0.85 * s, 1.0, 0.0, e.merchant, p.dba_name or p.legal_name,
                                      [f"Name matches '{e.merchant}' in the manual's named list (p.{e.page})"], [], mcc.page))
    floor = max(0.25, 0.45 * cands[0].score) if cands else 1
    probes = applicable([c.code for c in cands[:6] if c.score >= floor])
    cands = apply_probes(cands, probes, p.probe_answers)[:top]
    # structural checks that need numbers
    findings = checks(p, cands)
    # per-line classification
    secondary = []
    if len(sales) > 1:
        top_code = cands[0].code if cands else ""
        for s in sorted(sales, key=lambda s: -s.pct):
            cs = rank_text(s.text, p, top=3)
            if cs:
                secondary.append({"text": s.text, "pct": s.pct, "mcc": cs[0].code, "title": cs[0].title, "score": cs[0].score,
                                  "differs": cs[0].code != top_code})
    conf, note = _confidence(cands, bool(p.probe_answers))
    a = Assessment(p, cands, conf, note, probes, findings, secondary, named, cands[0].code if cands else "")
    a.findings += line_findings(a)
    return a


def checks(p: Profile, cands: list[Candidate]) -> list[Finding]:
    out: list[Finding] = []
    cfg = config()
    top = cands[0].code if cands else ""
    for c in cands[:1]:
        for fl in c.flags:
            out.append(Finding("warn", f"{c.code}: {fl}", "", ""))
    if top == "5411" and p.perishables_pct is not None and p.perishables_pct < 45:
        out.append(Finding("warn", "5411 test not met",
                           f"Perishables are {p.perishables_pct:.0f}% of monthly sales. The definition of 5411 sets a 45% test. Consider 5499, 5311, 5399 or 5300.", "Manual MCC 5411 definition"))
    if top == "5411" and p.perishables_pct is None:
        out.append(Finding("info", "Ask for the perishables share", "The grocery MCC 5411 carries a 45% perishables test in its definition. Ask the merchant for the share.", "Manual MCC 5411 definition"))
    if top == "5818":
        mt = cfg.get("min_annual_txn_5818", 25000000)
        if p.annual_txn is not None and p.annual_txn < mt:
            out.append(Finding("block", "5818 threshold not met", f"5818 is for large digital goods merchants with at least {mt:,} transactions a year outside Europe. This merchant reports {p.annual_txn:,}. Consider 5817 or 5815.", "Manual MCC 5818 definition"))
        elif p.annual_txn is None:
            out.append(Finding("warn", "Confirm volume for 5818", f"Needs {mt:,} transactions a year (all regions except Europe), a different test applies in Europe.", "Manual MCC 5818 definition"))
    if p.pay_at_pump:
        out.append(Finding("warn", "Automated fuel needs its own MCC", "Pay-at-pump sales must be set up under 5542, separate from any attended fuel or shop MCC.", rules.get("MULTI-1").ref))
    if p.cash_or_quasi_cash:
        out.append(Finding("warn", "Cash and quasi-cash handling", "Use the cash MCCs (6010, 6011) or quasi-cash MCCs (6051, 6012, 4829) for those lines, and set the special condition and quasi-cash indicators.", rules.get("MULTI-2").ref))
    if p.gambling:
        out.append(Finding("warn", "Gambling lines use 7995", "Card-present wagers use 7995 for the gambling transactions. For online gambling all transactions use 7995. US lotteries and gaming use 7800 to 7802. Registration with the network may apply.", rules.get("MULTI-5").ref))
    if p.is_marketplace_or_pf:
        out.append(Finding("warn", "Marketplace or payment facilitator", "Decide which one it is before assigning anything: a marketplace uses 5262 (registered), a payment facilitator is assigned an MCC for each sponsored merchant.", rules.get("NAME-2").ref + "; " + rules.get("MULTI-4").ref))
    if p.channel != CHANNELS[0]:
        out.append(Finding("info", "Card-absent location", "Location is the principal place of business, and the checkout must show the outlet's country on the page.", rules.get("LOC-2").ref + "; " + rules.get("LOC-3").ref))
    if top and kb.get(top) and "high_brand_risk_card_absent" in kb.get(top).tags and p.channel != CHANNELS[0]:
        out.append(Finding("warn", "High-brand-risk (card-absent)", "Check the network's high-brand-risk registration and acquirer obligations. Some regions limit this to non-domestic activity for 5912 and 5993.", rules.get("HBR-1").ref))
    if p.sells_digital_goods and top not in {"5817", "5815", "5816", "5818", "4899", "5735", "5192", "5942", "5994"}:
        out.append(Finding("info", "Digital goods sold", "Check whether the digital goods are a main line (5817, 5815, 5818) or only a minor line of a business with its own MCC.", ""))
    out.append(Finding("info", "One MCC per outlet, by main line of business", "The MCC follows the primary business by sales volume; a miscellaneous MCC only if no specific one fits.", rules.get("MCC-1").ref + "; " + rules.get("MCC-2").ref))
    return out


def line_findings(a: Assessment) -> list[Finding]:
    out = []
    diff = [s for s in a.secondary if s["differs"] and s["pct"] >= 1]
    for s in diff:
        out.append(Finding("info", f"Sales line '{s['text'][:40]}' ({s['pct']:.0f}%) fits {s['mcc']}",
                           "If this is a separate business (different name, distinct area or separate POS), it needs its own MCC. If it is part of the same business, keep the primary MCC.",
                           rules.get("MCC-4").ref + "; " + rules.get("MULTI-3").ref))
    for c in a.candidates[:1]:
        m = kb.get(c.code)
        if m and ("high_brand_risk_card_absent" in m.tags or "high_brand_risk_conditional" in m.tags):
            pass
    for s in a.secondary:
        m = kb.get(s["mcc"])
        if m and s["pct"] < 50 and ("high_brand_risk_card_absent" in m.tags or "gambling" in m.tags):
            out.append(Finding("warn", f"High-brand-risk or gambling line ({s['mcc']}) even at {s['pct']:.0f}% of sales", "Such a line needs its own MCC regardless of its share.", rules.get("MULTI-6").ref))
    return out


# ------------------------------------------------------------------ existing MCC review
def review(p: Profile, a: Assessment | None = None) -> dict:
    a = a or assess(p)
    code = str(p.current_mcc).strip().zfill(4) if str(p.current_mcc).strip() else ""
    cur = kb.get(code) if code else None
    res = {"current": code, "current_title": cur.title if cur else "", "verdict": "", "level": "", "why": [], "suggested": a.primary}
    if not code:
        res.update(verdict="No current MCC given", level="info")
        return res
    if cur is None:
        res.update(verdict="MCC code not in the list", level="block", why=["The code does not appear in the MCC list of this edition."])
        return res
    flag = _adjust(None, p, cur)
    if flag[0] == 0.0:
        res.update(verdict="MCC cannot be assigned to a merchant", level="block", why=flag[2])
        return res
    codes = [c.code for c in a.candidates]
    sc = {c.code: c.score for c in a.candidates}
    if code == a.primary:
        res.update(verdict="Consistent", level="ok", why=["The current MCC is the best match for the description and answers."])
    elif code in codes[:3] and sc[code] >= 0.8 * sc[a.primary]:
        res.update(verdict="Plausible, check the alternatives", level="warn",
                   why=[f"The current MCC is a close second to {a.primary}. Answer the probe questions or ask for the sales split."])
    elif code in codes:
        res.update(verdict="Weak fit, review", level="warn", why=[f"The current MCC ranks #{codes.index(code)+1}; {a.primary} fits the description better."])
    else:
        res.update(verdict="Does not fit the description", level="block", why=[f"The description does not match the definition of {code}. Best match: {a.primary}."])
    if flag[2]:
        res["why"] += flag[2]
    return res
