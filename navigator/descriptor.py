"""Descriptor checks: merchant name (25 characters), city field (13 characters) and supplementary data formats.

Limits and formats follow the manual's summaries in rules.py (pages given there). Abbreviation suggestions are the
Navigator's own and must be reviewed by a person; the manual asks that the identifying part of the name is not truncated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import kb, rules

NAME_MAX, CITY_MAX = 25, 13
LEGAL = [r"\bPRIVATE\b", r"\bPVT\b", r"\bLIMITED\b", r"\bLTD\b", r"\bLLP\b", r"\bINC\b", r"\bLLC\b", r"\bCORPORATION\b", r"\bCORP\b", r"\bCO\b", r"\(INDIA\)"]
ABBREV = {"INTERNATIONAL": "INTL", "SERVICES": "SVCS", "SERVICE": "SVC", "TECHNOLOGIES": "TECH", "TECHNOLOGY": "TECH", "ENTERPRISES": "ENT",
          "RESTAURANT": "REST", "COMMUNICATIONS": "COMM", "SOLUTIONS": "SOL", "DEPARTMENT": "DEPT", "STORES": "STR", "STORE": "STR",
          "ELECTRONICS": "ELEC", "TRADING": "TRDG", "INDUSTRIES": "IND", "MANAGEMENT": "MGMT", "NATIONAL": "NATL", "CENTER": "CTR", "CENTRE": "CTR"}
TYPES = ["Merchant", "Payment facilitator (sponsored merchant)", "Billing provider or bill-payment service", "Tip (separate transaction)", "Marketplace seller"]


@dataclass
class Check:
    level: str
    text: str
    ref: str = ""


@dataclass
class DescriptorResult:
    name_field: str
    city_field: str
    checks: list = field(default_factory=list)
    suggestion: str = ""


def clean_name(name: str) -> str:
    s = name.upper()
    for pat in LEGAL:
        s = re.sub(pat, " ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 &'*.\-/]", " ", s)).strip()


def shorten(name: str) -> str:
    s = clean_name(name)
    if len(s) <= NAME_MAX:
        return s
    words = [ABBREV.get(w, w) for w in s.split()]
    s = " ".join(words)
    while len(s) > NAME_MAX and len(words) > 2:
        words = words[:-1]
        s = " ".join(words)
    return s[:NAME_MAX].rstrip()


def compose(kind: str, name: str, extra: str = "") -> str:
    n = clean_name(name)
    if kind.startswith("Payment"):
        return f"PF*{n}"
    if kind.startswith("Billing"):
        return f"{n}*{clean_name(extra)}" if extra else n
    if kind.startswith("Tip"):
        return f"{n} Tip".upper()
    if kind.startswith("Marketplace"):
        return f"{n}*{clean_name(extra)}" if extra else n
    return n


def check(kind: str, name: str, city: str, extra: str = "", card_absent: bool = False, mcc: str = "") -> DescriptorResult:
    composed = compose(kind, name, extra)
    r = DescriptorResult(composed, city.upper().strip())
    ch = r.checks
    if not name.strip():
        ch.append(Check("block", "Enter the name customers recognise (the DBA name)", rules.get("NAME-1").ref))
        return r
    if len(composed) > NAME_MAX:
        sug = shorten(name)
        full = compose(kind, sug, extra)
        r.suggestion = full
        ch.append(Check("block" if len(full) > NAME_MAX else "warn",
                        f"Name is {len(composed)} characters; the field holds {NAME_MAX}. Suggested short form: '{full}' ({len(full)}). Keep the identifying part of the name.", rules.get("NAME-3").ref))
    else:
        ch.append(Check("ok", f"Name fits ({len(composed)} of {NAME_MAX} characters)", rules.get("NAME-3").ref))
    if kind.startswith("Payment"):
        ch.append(Check("info", "Payment facilitator format is PF*Sponsored merchant; each sponsored merchant also has its own MCC and location", rules.get("NAME-6").ref + "; " + rules.get("MULTI-4").ref))
    if kind.startswith("Billing"):
        ch.append(Check("info", "Billing-provider and bill-payment services use name*supplier or name*biller; confirm the exact form on the manual page", rules.get("NAME-6").ref))
    if kind.startswith("Marketplace"):
        ch.append(Check("info", "Marketplace transactions follow the manual's marketplace naming format; confirm the exact form on the manual page", rules.get("NAME-5").ref + " (see the supplementary data section)"))
    if kind.startswith("Tip"):
        ch.append(Check("info", "A tip collected as a separate transaction carries the word Tip", rules.get("NAME-7").ref))
    if re.search(r"\d{5,}|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(inv|invoice|order|ord|ref)\W*\d+", name, re.I):
        ch.append(Check("warn", "The name looks like it contains an order number, invoice or date. Supplementary data must be the same on every transaction", rules.get("NAME-4").ref))
    if re.search(r"[^\x20-\x7E]", name):
        ch.append(Check("warn", "Non-ASCII characters in the name; check the character set accepted in your authorisation and clearing interfaces", ""))
    if mcc and kb.get(mcc):
        m = kb.get(mcc)
        words = {w.lower().rstrip("s") for w in re.findall(r"[A-Za-z]{4,}", m.title + " " + " ".join(m.included[:20]))}
        nameset = {w.lower().rstrip("s") for w in re.findall(r"[A-Za-z]{4,}", name)}
        if not words & nameset:
            ch.append(Check("info", f"The name does not hint at the business type of {mcc} ({m.short_title}). If customers would not recognise it, add type information", rules.get("NAME-1").ref))
    c = city.strip()
    if not c:
        ch.append(Check("warn", "City field is empty", rules.get("CITY-1").ref))
    elif len(c) > CITY_MAX:
        contact = bool(re.search(r"\d{6,}|https?://|www\.|\.[a-z]{2,}\b|@", c, re.I))
        lvl = "warn" if (card_absent and contact) else "block"
        extra = " It looks like a contact detail for a card-absent merchant; confirm how the manual and your interface specs handle length for that case." if lvl == "warn" else ""
        ch.append(Check(lvl, f"City is {len(c)} characters; the field holds {CITY_MAX}. The city is spelled out with limited exceptions (see the city field section)." + extra, rules.get("CITY-1").ref))
    else:
        ch.append(Check("ok", f"City fits ({len(c)} of {CITY_MAX})", rules.get("CITY-1").ref))
    if card_absent:
        if not re.search(r"\d{6,}|https?://|www\.|\.[a-z]{2,}\b|@", c, re.I):
            ch.append(Check("warn", "Card-absent: the field should carry a customer service phone number, URL or email", rules.get("CITY-2").ref))
        else:
            ch.append(Check("ok", "Card-absent contact detail present", rules.get("CITY-2").ref))
    if mcc in {"4111", "4112", "4131"}:
        ch.append(Check("info", "Transit MCCs have their own city-field allowances", rules.get("CITY-3").ref))
    return r
